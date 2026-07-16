from __future__ import annotations

import asyncio
import threading
from typing import Any, Dict, Optional

from rustplus import ChatEvent, EntityEvent, RustSocket, ServerDetails, TeamEvent
from rustplus.remote.camera.camera_constants import CameraMovementOptions
from rustplus.structs import RustError
from rustplus.structs.util import Vector

from services.rustplus.alert_manager import AlertManager
from services.rustplus.cargo_tracker import CargoTracker
from services.rustplus.chat_commands import ChatCommandHandler
from services.rustplus.event_bus import EventBus, EventType
from services.rustplus.event_tracker import LiveEventTracker, TeamTracker
from services.rustplus.live_format import format_markers, format_team, upkeep_hours_left
from services.rustplus.player_intel import PlayerIntelDB
from services.rustplus.shop_tracker import ShopTracker
from storage.rustplus_store import PairedServer, RustPlusStore


class ConnectionManager:
    """Один WebSocket к активному серверу (asyncio в фоновом потоке)."""

    def __init__(self, store: RustPlusStore, event_bus: EventBus) -> None:
        self._store = store
        self._bus = event_bus
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._loop_ready = threading.Event()
        self._socket: Optional[RustSocket] = None
        self._connected_server: Optional[PairedServer] = None
        self._poll_task: Optional[asyncio.Task] = None
        self._running = False
        self._map_size: Optional[int] = None
        self._registered_entities: set[int] = set()
        self._event_tracker = LiveEventTracker()
        self._team_tracker = TeamTracker()
        self._cargo_tracker = CargoTracker()
        self._shop_tracker = ShopTracker()
        self._player_intel = PlayerIntelDB()
        self._alert_manager = AlertManager(store)
        self._server_time_raw: Optional[float] = None
        self._team_cache: Dict[str, Any] = {}
        self._markers_cache: Dict[str, Any] = {}
        self._upkeep_warned: set[int] = set()
        self._chat_commands: Optional[ChatCommandHandler] = None
        self._camera_manager = None
        self._camera_id: Optional[str] = None
        self._camera_frame_task: Optional[asyncio.Task] = None
        self._camera_controls: Dict[str, bool] = {}
        self._stay_connected = False
        self._reconnect_task: Optional[asyncio.Task] = None
        self._poll_failures = 0
        self._POLL_REQUEST_TIMEOUT_SEC = 15.0
        self._MAX_POLL_FAILURES = 3
        self._RECONNECT_DELAYS_SEC = (3, 5, 10, 20, 30, 60)
        self._POLL_INTERVAL_MIN_SEC = 5
        self._POLL_INTERVAL_MAX_SEC = 20
        self._POLL_INTERVAL_DEFAULT_SEC = 10

    @property
    def is_connected(self) -> bool:
        return self._connected_server is not None and self._socket_alive()

    @property
    def connected_server(self) -> Optional[PairedServer]:
        return self._connected_server

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._stay_connected = False
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._disconnect(intentional=True), self._loop)
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self._thread = None

    def connect(self, server: PairedServer) -> None:
        self._stay_connected = True
        self.start()
        if not self._loop_ready.wait(timeout=5.0):
            self._bus.emit(EventType.ERROR, message="Подключение: event loop не запустился")
            return
        assert self._loop is not None
        asyncio.run_coroutine_threadsafe(self._connect(server), self._loop)

    def disconnect(self) -> None:
        self._stay_connected = False
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._disconnect(intentional=True), self._loop)

    def send_team_message(self, text: str) -> None:
        if not self._loop:
            return
        if not self.is_connected:
            self._bus.emit(EventType.ERROR, message="Чат: сначала подключитесь к серверу")
            return
        asyncio.run_coroutine_threadsafe(self._send_chat(text), self._loop)

    def set_entity_value(self, entity_id: int, value: bool) -> None:
        if not self._loop or not self.is_connected:
            return
        asyncio.run_coroutine_threadsafe(self._set_entity(entity_id, value), self._loop)

    def fetch_map(self) -> None:
        if not self._loop or not self.is_connected:
            self._bus.emit(EventType.ERROR, message="Карта: сначала подключитесь к серверу")
            return
        asyncio.run_coroutine_threadsafe(self._fetch_map(), self._loop)

    def refresh_devices(self) -> None:
        if not self._loop or not self.is_connected or not self._socket or not self._connected_server:
            return
        asyncio.run_coroutine_threadsafe(self._refresh_device_handlers(), self._loop)

    def refresh_device_states(self) -> None:
        if not self._loop or not self.is_connected:
            return
        asyncio.run_coroutine_threadsafe(self._refresh_device_states(), self._loop)

    def open_camera(self, camera_id: str) -> None:
        if not self._loop or not self.is_connected:
            self._bus.emit(EventType.ERROR, message="Камера: сначала подключитесь к серверу")
            return
        future = asyncio.run_coroutine_threadsafe(self._open_camera(camera_id), self._loop)

        def _report(done) -> None:
            try:
                done.result()
            except Exception as exc:
                self._bus.emit(EventType.ERROR, message=f"Камера: {exc}")

        future.add_done_callback(_report)

    def close_camera(self) -> None:
        if not self._loop:
            return
        asyncio.run_coroutine_threadsafe(self._close_camera(), self._loop)

    def camera_send_movement(self, movements: Optional[list[int]] = None) -> None:
        if not self._loop or not self._camera_manager:
            return
        asyncio.run_coroutine_threadsafe(
            self._camera_send_movement(movements or []), self._loop,
        )

    def camera_send_look(self, dx: float, dy: float) -> None:
        if not self._loop or not self._camera_manager:
            return
        asyncio.run_coroutine_threadsafe(self._camera_send_look(dx, dy), self._loop)

    @property
    def active_camera_id(self) -> Optional[str]:
        return self._camera_id

    @property
    def camera_controls(self) -> Dict[str, bool]:
        return dict(self._camera_controls)

    def toggle_group(self, group_id: str, action: str) -> None:
        if not self._loop or not self.is_connected:
            return
        asyncio.run_coroutine_threadsafe(self._toggle_group(group_id, action), self._loop)

    def toggle_entity(self, entity_id: int, action: str) -> None:
        if not self._loop or not self.is_connected:
            return
        asyncio.run_coroutine_threadsafe(self._toggle_entity(entity_id, action), self._loop)

    def get_entity_info_sync(self, entity_id: int) -> Any:
        if not self._loop or not self.is_connected:
            return None
        future = asyncio.run_coroutine_threadsafe(self._get_entity_info(entity_id), self._loop)
        try:
            return future.result(timeout=5)
        except Exception:
            return None

    @property
    def team_cache(self) -> Dict[str, Any]:
        return dict(self._team_cache)

    @property
    def markers_cache(self) -> Dict[str, Any]:
        return dict(self._markers_cache)

    @property
    def server_time_raw(self) -> Optional[float]:
        return self._server_time_raw

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop_ready.set()
        try:
            self._loop.run_forever()
        finally:
            self._loop_ready.clear()
            pending = asyncio.all_tasks(self._loop)
            for task in pending:
                task.cancel()
            self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            self._loop.close()

    async def _connect(self, server: PairedServer) -> None:
        await self._cancel_reconnect()
        await self._disconnect()

        last_error: Optional[Exception] = None
        for use_proxy in (False, True):
            label = "Facepunch proxy" if use_proxy else "прямое"
            self._bus.emit(
                EventType.STATUS,
                message=f"Подключение ({label}) к {server.name}...",
            )
            try:
                await self._connect_once(server, use_proxy=use_proxy)
                return
            except ConnectionError as exc:
                last_error = exc
                if "not_found" not in str(exc):
                    break
            except Exception as exc:
                last_error = exc
                break

        self._socket = None
        self._connected_server = None
        self._bus.emit(EventType.ERROR, message=f"Подключение: {last_error}")

    async def _connect_once(self, server: PairedServer, use_proxy: bool = False) -> None:
        details = ServerDetails(
            server.ip,
            server.port,
            server.player_id,
            server.player_token,
        )

        socket: Optional[RustSocket] = None
        try:
            socket = RustSocket(details, use_fp_proxy=use_proxy)

            connected = await socket.connect()
            if not connected:
                raise ConnectionError(
                    f"Сервер {server.ip}:{server.port} отклонил WebSocket-подключение"
                )

            await self._validate_session(socket, server)

            self._socket = socket
            self._connected_server = server
            self._store.set_active_server_id(server.id)
            self._bus.emit(EventType.CONNECTED, server_id=server.id, name=server.name)

            info = await socket.get_info()
            if isinstance(info, RustError):
                self._map_size = None
                self._bus.emit(
                    EventType.SERVER_INFO,
                    name=server.name,
                    players=None,
                    max_players=None,
                    wipe_time=None,
                    map_name=None,
                    map_size=None,
                    warning=self._format_rust_error(info),
                )
            else:
                self._map_size = getattr(info, "size", None)
                self._bus.emit(
                    EventType.SERVER_INFO,
                    name=getattr(info, "name", server.name),
                    players=getattr(info, "players", None),
                    max_players=getattr(info, "max_players", None),
                    wipe_time=getattr(info, "wipe_time", None),
                    map_name=getattr(info, "map", None),
                    map_size=self._map_size,
                )

            self._registered_entities.clear()
            self._register_chat_team(socket, details)
            self._register_entity_handlers(socket, details, server)
            self._chat_commands = ChatCommandHandler(
                self._store,
                send_message=lambda text: self.send_team_message(text),
                set_entity=self.set_entity_value,
                get_entity_info=self.get_entity_info_sync,
                get_server_time_raw=lambda: self._server_time_raw,
                get_team=lambda: self._team_cache,
                get_map_size=lambda: self._map_size,
            )
            self._cargo_tracker = CargoTracker(
                send_chat=lambda text: self.send_team_message(text),
            )

            if self._poll_task:
                self._poll_task.cancel()
            self._poll_task = asyncio.create_task(self._poll_loop())
            asyncio.create_task(self._refresh_device_states())
        except Exception:
            if socket is not None:
                try:
                    await socket.disconnect()
                except Exception:
                    pass
            raise

    async def _validate_session(self, socket: RustSocket, server: PairedServer) -> None:
        retries = 4
        delay_sec = 3.0
        last_reason = "not_found"

        for attempt in range(retries):
            time_result = await socket.get_time()
            if not isinstance(time_result, RustError):
                return

            last_reason = time_result.reason
            if last_reason != "not_found":
                break

            if attempt < retries - 1:
                self._bus.emit(
                    EventType.STATUS,
                    message=(
                        f"Сервер ещё не принял токен, повтор {attempt + 2}/{retries} "
                        f"({server.ip}:{server.port}, token ...{str(server.player_token)[-4:]})"
                    ),
                )
                await asyncio.sleep(delay_sec)

        raise ConnectionError(self._not_found_help(last_reason, server))

    async def _disconnect(self, *, intentional: bool = False) -> None:
        if intentional:
            self._stay_connected = False
        await self._cancel_reconnect()
        if self._poll_task:
            self._poll_task.cancel()
            self._poll_task = None
        if self._socket:
            try:
                await self._socket.disconnect()
            except Exception:
                pass
        self._socket = None
        server_id = self._connected_server.id if self._connected_server else None
        self._connected_server = None
        self._map_size = None
        self._registered_entities.clear()
        self._event_tracker.reset()
        self._team_tracker.reset()
        self._cargo_tracker.reset()
        self._shop_tracker.reset()
        self._server_time_raw = None
        self._team_cache = {}
        self._markers_cache = {}
        self._upkeep_warned.clear()
        self._chat_commands = None
        await self._close_camera()
        if server_id:
            self._bus.emit(EventType.DISCONNECTED, server_id=server_id)

    async def _send_chat(self, text: str) -> None:
        if not self._socket:
            return
        try:
            # Как в rustplus.py: send без ожидания ответа — сервер часто
            # возвращает message_not_sent, хотя сообщение доставлено в чат.
            await self._socket.send_team_message(text)
            self._bus.emit(EventType.STATUS, message="Сообщение отправлено в team chat")
        except Exception as exc:
            self._bus.emit(EventType.ERROR, message=f"Чат: {exc}")

    async def _set_entity(self, entity_id: int, value: bool) -> None:
        if not self._socket:
            return
        try:
            await self._socket.set_entity_value(entity_id, value)
        except Exception as exc:
            self._bus.emit(EventType.ERROR, message=f"Устройство: {exc}")

    def _register_chat_team(self, socket: RustSocket, details: ServerDetails) -> None:
        @ChatEvent(details)
        async def on_chat(event):
            payload = getattr(event, "message", event)
            name = str(getattr(payload, "name", "Unknown") or "Unknown")
            raw_message = getattr(payload, "message", "")
            message = str(raw_message or "")
            steam_id = getattr(payload, "steam_id", None)
            self._bus.emit(
                EventType.CHAT_MESSAGE,
                name=name,
                message=message,
                steam_id=steam_id,
            )
            if self._chat_commands:
                self._chat_commands.handle(name, message, steam_id)

        @TeamEvent(details)
        async def on_team(event):
            payload = format_team(event, self._map_size)
            self._team_cache = payload
            self._bus.emit(EventType.TEAM_INFO, **payload)
            if self._connected_server:
                self._player_intel.record_team(self._connected_server.id, payload.get("members", []))
            for death in self._team_tracker.detect_deaths(payload.get("members", [])):
                await self._notify_team_death(death)

    def _register_entity_handlers(
        self, socket: RustSocket, details: ServerDetails, server: PairedServer
    ) -> None:
        for device in self._store.list_devices(server.id):
            if device.entity_id in self._registered_entities:
                continue
            self._registered_entities.add(device.entity_id)
            entity_id = device.entity_id

            @EntityEvent(details, entity_id)
            async def on_entity(event, eid=entity_id, dev=device):
                value = getattr(event, "value", None)
                self._bus.emit(
                    EventType.ENTITY_CHANGED,
                    entity_id=eid,
                    value=value,
                )
                if dev.device_type == "smart_alarm" and value:
                    if self._alert_manager.should_emit("alarm"):
                        self._bus.emit(
                            EventType.LIVE_ALERT,
                            title=dev.name,
                            message=f"🚨 {dev.name}: тревога!",
                            category="alarm",
                        )
                        self._alert_manager.play_alarm()

    async def _refresh_device_handlers(self) -> None:
        if not self._socket or not self._connected_server:
            return
        details = ServerDetails(
            self._connected_server.ip,
            self._connected_server.port,
            self._connected_server.player_id,
            self._connected_server.player_token,
        )
        self._register_entity_handlers(self._socket, details, self._connected_server)

    async def _refresh_device_states(self) -> None:
        if not self._socket or not self._connected_server:
            return
        server = self._connected_server
        for device in self._store.list_devices(server.id):
            try:
                info = await self._socket.get_entity_info(device.entity_id)
                if isinstance(info, RustError):
                    continue
                self._bus.emit(
                    EventType.ENTITY_CHANGED,
                    entity_id=device.entity_id,
                    value=getattr(info, "value", None),
                    capacity=getattr(info, "capacity", None),
                    items=len(getattr(info, "items", []) or []),
                    has_protection=getattr(info, "has_protection", None),
                    protection_expiry=getattr(info, "protection_expiry", None),
                )
                if device.device_type == "storage_monitor":
                    await self._check_upkeep_alert(device, info)
            except Exception:
                continue

    async def _fetch_map(self) -> None:
        if not self._socket:
            return
        try:
            from app_paths import get_rustplus_dir

            self._bus.emit(EventType.STATUS, message="Загрузка карты...")
            alerts = self._store.get_alert_settings()
            layers = self._store.get_map_layers()
            map_image = await self._socket.get_map(
                add_icons=layers.monuments,
                add_events=alerts.cargo,
                add_vending_machines=layers.shops,
                add_team_positions=layers.players,
                add_grid=True,
            )
            if isinstance(map_image, RustError):
                self._bus.emit(EventType.ERROR, message=f"Карта: {map_image.reason}")
                return

            path = get_rustplus_dir() / "map_live.jpg"
            if map_image.mode != "RGB":
                map_image = map_image.convert("RGB")
            map_image.save(path, format="JPEG", quality=85)
            self._bus.emit(EventType.MAP_IMAGE, path=str(path))
            self._bus.emit(EventType.STATUS, message="Карта обновлена")
        except Exception as exc:
            self._bus.emit(EventType.ERROR, message=f"Карта: {exc}")

        self._poll_failures = 0
        if server_id:
            self._bus.emit(EventType.DISCONNECTED, server_id=server_id)

    def _socket_alive(self) -> bool:
        socket = self._socket
        if socket is None:
            return False
        ws = getattr(socket, "ws", None)
        if ws is None:
            return False
        task = getattr(ws, "task", None)
        if task is not None and task.done():
            return False
        connection = getattr(ws, "connection", None)
        if connection is None:
            return False
        if getattr(connection, "closed", False):
            return False
        return bool(getattr(ws, "open", False))

    @staticmethod
    def _is_connection_lost_error(exc: BaseException) -> bool:
        if isinstance(exc, (ConnectionError, ConnectionResetError, BrokenPipeError)):
            return True
        if isinstance(exc, OSError):
            winerror = getattr(exc, "winerror", None)
            if winerror in {10054, 10053, 121}:
                return True
        message = str(exc).lower()
        markers = (
            "connection interrupted",
            "no close frame",
            "websocket",
            "message failed to send",
            "no response received",
            "data transfer failed",
            "превышен таймаут семафора",
            "semaphore timeout",
        )
        return any(marker in message for marker in markers)

    async def _cancel_reconnect(self) -> None:
        if not self._reconnect_task:
            return
        self._reconnect_task.cancel()
        try:
            await self._reconnect_task
        except asyncio.CancelledError:
            pass
        self._reconnect_task = None

    async def _handle_connection_lost(self, reason: str) -> None:
        server = self._connected_server
        if not server:
            return
        self._bus.emit(
            EventType.STATUS,
            message=f"Соединение потеряно ({reason}). Переподключение...",
        )
        await self._disconnect()
        if not self._running or not self._stay_connected:
            return
        if self._reconnect_task and not self._reconnect_task.done():
            return
        self._reconnect_task = asyncio.create_task(self._reconnect_loop(server))

    async def _reconnect_loop(self, server: PairedServer) -> None:
        for index, delay in enumerate(self._RECONNECT_DELAYS_SEC):
            if not self._running or not self._stay_connected:
                return
            if index > 0:
                self._bus.emit(
                    EventType.STATUS,
                    message=f"Повтор подключения к {server.name} через {delay} с...",
                )
                await asyncio.sleep(delay)
            try:
                await self._connect(server)
                if self.is_connected:
                    self._bus.emit(
                        EventType.STATUS,
                        message=f"Снова подключено к {server.name}",
                    )
                    return
            except Exception as exc:
                self._bus.emit(EventType.ERROR, message=f"Переподключение: {exc}")
        self._stay_connected = False
        self._bus.emit(
            EventType.ERROR,
            message="Не удалось восстановить соединение с сервером",
        )

    async def _poll_request(self, coro):
        return await asyncio.wait_for(coro, timeout=self._POLL_REQUEST_TIMEOUT_SEC)

    def _poll_interval_sec(self) -> float:
        raw = int(getattr(self._store.get_settings(), "poll_interval_sec", self._POLL_INTERVAL_DEFAULT_SEC))
        clamped = max(self._POLL_INTERVAL_MIN_SEC, min(self._POLL_INTERVAL_MAX_SEC, raw))
        return float(clamped)

    async def _poll_loop(self) -> None:
        while self._running and self._socket:
            if not self._socket_alive():
                await self._handle_connection_lost("WebSocket закрыт")
                break
            try:
                time_info = await self._poll_request(self._socket.get_time())
                if isinstance(time_info, RustError):
                    self._poll_failures += 1
                    if self._poll_failures >= self._MAX_POLL_FAILURES:
                        await self._handle_connection_lost(time_info.reason or "get_time")
                        break
                else:
                    self._poll_failures = 0
                    self._server_time_raw = time_info.raw_time
                    self._bus.emit(
                        EventType.SERVER_TIME,
                        time=time_info.time,
                        raw_time=time_info.raw_time,
                    )

                team = await self._poll_request(self._socket.get_team_info())
                if isinstance(team, RustError):
                    self._poll_failures += 1
                else:
                    self._poll_failures = 0
                    payload = format_team(team, self._map_size)
                    self._team_cache = payload
                    self._bus.emit(EventType.TEAM_INFO, **payload)
                    if self._connected_server:
                        self._player_intel.record_team(self._connected_server.id, payload.get("members", []))
                    for death in self._team_tracker.detect_deaths(payload.get("members", [])):
                        await self._notify_team_death(death)

                markers = await self._poll_request(self._socket.get_markers())
                if isinstance(markers, RustError):
                    self._poll_failures += 1
                else:
                    self._poll_failures = 0
                    payload = format_markers(markers, self._map_size)
                    self._markers_cache = payload
                    self._bus.emit(EventType.MARKERS, **payload)
                    for event in self._event_tracker.detect_new(payload.get("events", [])):
                        category = self._event_category(event)
                        if self._alert_manager.should_emit(category):
                            self._bus.emit(
                                EventType.LIVE_ALERT,
                                title=event.get("type_name", "Событие"),
                                grid=event.get("grid", "?"),
                                message=f"{event.get('type_name', 'Событие')} — {event.get('grid', '?')}",
                                category=category,
                            )
                    cargo_msg = self._cargo_tracker.update(payload.get("events", []))
                    if cargo_msg and self._alert_manager.should_emit("cargo"):
                        self._bus.emit(
                            EventType.LIVE_ALERT,
                            title="Карго",
                            message=cargo_msg,
                            category="cargo",
                        )
                    for alert in self._shop_tracker.detect_changes(
                        payload.get("vendors", []),
                        alerts_enabled=self._alert_manager.should_emit("shop"),
                    ):
                        self._bus.emit(
                            EventType.LIVE_ALERT,
                            title=alert["title"],
                            message=alert["message"],
                            category="shop",
                        )
                if self._poll_failures >= self._MAX_POLL_FAILURES:
                    await self._handle_connection_lost("нет ответа от сервера")
                    break
            except asyncio.CancelledError:
                break
            except Exception as exc:
                if self._is_connection_lost_error(exc):
                    await self._handle_connection_lost(str(exc))
                    break
                self._poll_failures += 1
                self._bus.emit(EventType.ERROR, message=f"Polling: {exc}")
                if self._poll_failures >= self._MAX_POLL_FAILURES:
                    await self._handle_connection_lost(str(exc))
                    break
            await asyncio.sleep(self._poll_interval_sec())

    async def _notify_team_death(self, death: Dict[str, Any]) -> None:
        name = death.get("name", "Игрок")
        grid = death.get("grid", "?")
        message = f"💀 {name} погиб [{grid}]"
        if self._connected_server:
            self._store.add_death_marker(self._connected_server.id, death)
        if self._alert_manager.should_emit("death"):
            self._bus.emit(
                EventType.LIVE_ALERT,
                title="Смерть в команде",
                message=message,
                category="death",
            )
        if not self._socket:
            return
        try:
            await self._socket.send_team_message(message)
        except Exception:
            pass

    async def _get_entity_info(self, entity_id: int) -> Any:
        if not self._socket:
            return None
        try:
            info = await self._socket.get_entity_info(entity_id)
            if isinstance(info, RustError):
                return None
            return info
        except Exception:
            return None

    async def _check_upkeep_alert(self, device, info) -> None:
        if not getattr(info, "has_protection", False):
            return
        hours = upkeep_hours_left(getattr(info, "protection_expiry", 0), self._server_time_raw or 0)
        if hours is None or hours >= 1:
            return
        if device.entity_id in self._upkeep_warned:
            return
        self._upkeep_warned.add(device.entity_id)
        mins = int(hours * 60)
        self._bus.emit(
            EventType.LIVE_ALERT,
            title="Upkeep",
            message=f"⚠ {device.name}: upkeep < 1 ч ({mins} мин)",
            category="alarm",
        )

    async def _toggle_entity(self, entity_id: int, action: str) -> None:
        if not self._socket:
            return
        if action == "on":
            await self._set_entity(entity_id, True)
        elif action == "off":
            await self._set_entity(entity_id, False)
        else:
            info = await self._get_entity_info(entity_id)
            current = bool(getattr(info, "value", False)) if info else False
            await self._set_entity(entity_id, not current)

    async def _toggle_group(self, group_id: str, action: str) -> None:
        group = next((g for g in self._store.list_device_groups() if g.id == group_id), None)
        if not group or not self._socket:
            return
        devices = {d.id: d for d in self._store.list_devices(group.server_id)}
        for device_id in group.device_ids:
            device = devices.get(device_id)
            if not device or device.device_type != "smart_switch":
                continue
            await self._toggle_entity(device.entity_id, action)

    @staticmethod
    def _event_category(event: Dict[str, Any]) -> str:
        from rustplus.structs.rust_marker import RustMarker

        marker_type = event.get("type")
        if marker_type == RustMarker.CargoShipMarker:
            return "cargo"
        return "cargo"

    async def _open_camera(self, camera_id: str) -> None:
        cam_id = camera_id.strip()
        try:
            if not self._socket:
                self._bus.emit(EventType.ERROR, message="Камера: нет подключения")
                return

            print(f"[Rust+] _open_camera start {cam_id}")
            await self._close_camera()
            self._bus.emit(EventType.STATUS, message=f"Подключение к камере {cam_id}...")

            try:
                manager = await asyncio.wait_for(
                    self._socket.get_camera_manager(cam_id),
                    timeout=12.0,
                )
            except asyncio.TimeoutError:
                self._bus.emit(
                    EventType.ERROR,
                    message=f"Камера: таймаут подписки на {cam_id}. Закройте мобильный Rust+ и проверьте ID.",
                )
                print(f"[Rust+] camera timeout {cam_id}")
                return

            if isinstance(manager, RustError):
                reason = str(manager.reason or "")
                friendly = {
                    "player_online": (
                        "Камера недоступна: вы онлайн на сервере. "
                        "Выйдите из игры (в меню / sleeper) и откройте снова."
                    ),
                    "not_found": f"Камера не найдена: {cam_id}. Проверьте ID на дроне/CCTV.",
                    "access_denied": "Камера: нет доступа (не ваша сеть / чужой TC).",
                    "no_player": "Камера: персонаж не на сервере (нужен sleeper/offline).",
                }.get(reason.lower(), f"Камера: {reason}")
                self._bus.emit(EventType.ERROR, message=friendly)
                print(f"[Rust+] camera RustError {cam_id}: {reason}")
                return

            self._camera_manager = manager
            self._camera_id = cam_id
            self._camera_controls = {
                "movement": manager.can_move(CameraMovementOptions.MOVEMENT),
                "mouse": manager.can_move(CameraMovementOptions.MOUSE),
            }
            self._bus.emit(
                EventType.CAMERA_STATUS,
                open=True,
                camera_id=cam_id,
                **self._camera_controls,
            )
            self._bus.emit(EventType.STATUS, message=f"Камера открыта: {cam_id}")
            print(f"[Rust+] camera manager ready {cam_id} controls={self._camera_controls}")
            self._camera_frame_task = asyncio.create_task(self._camera_frame_loop())
        except Exception as exc:
            self._camera_manager = None
            self._camera_id = None
            self._camera_controls = {}
            self._bus.emit(EventType.ERROR, message=f"Камера: {exc}")
            print(f"[Rust+] camera exception {cam_id}: {exc}")
            raise

    async def _close_camera(self) -> None:
        if self._camera_frame_task:
            self._camera_frame_task.cancel()
            try:
                await self._camera_frame_task
            except asyncio.CancelledError:
                pass
            self._camera_frame_task = None

        if self._camera_manager:
            try:
                await self._camera_manager.exit_camera()
            except Exception:
                pass
        self._camera_manager = None
        closed_id = self._camera_id
        self._camera_id = None
        self._camera_controls = {}
        if closed_id:
            self._bus.emit(EventType.CAMERA_STATUS, open=False, camera_id=closed_id)

    async def _camera_frame_loop(self) -> None:
        import io
        import time

        try:
            while self._camera_manager and self._camera_manager._open:
                # Подписка Rust+ живёт ~15 с — нужно продлевать
                if time.time() - self._camera_manager.time_since_last_subscribe > 10:
                    await self._camera_manager.resubscribe()
                if self._camera_manager.has_frame_data():
                    frame = await self._camera_manager.get_frame(render_entities=True)
                    if frame is not None:
                        if frame.mode != "RGB":
                            frame = frame.convert("RGB")
                        buf = io.BytesIO()
                        frame.save(buf, format="JPEG", quality=75)
                        self._bus.emit(
                            EventType.CAMERA_FRAME,
                            data=buf.getvalue(),
                            camera_id=self._camera_id,
                        )
                await asyncio.sleep(0.08)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self._bus.emit(EventType.ERROR, message=f"Камера: {exc}")

    async def _camera_send_movement(self, movements: list[int]) -> None:
        if not self._camera_manager or not self._camera_controls.get("movement"):
            return
        try:
            if movements:
                await self._camera_manager.send_actions(movements)
            else:
                await self._camera_manager.clear_movement()
        except Exception:
            pass

    async def _camera_send_look(self, dx: float, dy: float) -> None:
        if not self._camera_manager or not self._camera_controls.get("mouse"):
            return
        if dx == 0 and dy == 0:
            return
        try:
            await self._camera_manager.send_mouse_movement(Vector(dx, dy))
        except Exception:
            pass

    @staticmethod
    def _format_rust_error(error: RustError) -> str:
        return f"{error.method}: {error.reason}"

    @staticmethod
    def _not_found_help(reason: str, server: Optional[PairedServer] = None) -> str:
        if reason != "not_found":
            return reason

        creds = ""
        if server:
            creds = (
                f"\n\nДанные паринга: {server.ip}:{server.port}, "
                f"Steam {server.player_id}, token ...{str(server.player_token)[-4:]}"
            )

        return (
            "Сервер не принял токен (not_found)."
            f"{creds}\n\n"
            "Что проверить:\n"
            "1) Вы онлайн на ЭТОМ сервере прямо сейчас\n"
            "2) Закройте мобильное приложение Rust+ (конфликт уведомлений)\n"
            "3) Listener активен → Pair Server → Resend notification 2-3 раза\n"
            "4) Сразу после уведомления нажмите Connect (не ждите)\n"
            "5) Проверьте Rust+ на телефоне — если там тоже не работает, "
            "проблема на стороне сервера (Rust+ у админов)"
        )
