from __future__ import annotations

import threading
from typing import Optional

from overlay.hotkey_util import add_hotkey_precise
from services.rustplus.connection_manager import ConnectionManager
from services.rustplus.event_bus import EventBus, EventType
from services.rustplus.fcm_bridge import FCMBridge
from services.rustplus.item_icons import ItemIconCache
from services.rustplus.map_renderer import MapRenderer
from services.rustplus.steam_avatars import SteamAvatarCache
from storage.rustplus_store import AlertSettings, AppSettings, MapLayerSettings, PairedServer, RustPlusStore


class RustPlusService:
    """Фасад live-модуля Rust+ (pairing + connection + events)."""

    def __init__(self) -> None:
        self.store = RustPlusStore()
        self.event_bus = EventBus()
        self.fcm = FCMBridge(self.event_bus, self.store)
        self.connection = ConnectionManager(self.store, self.event_bus)
        self.map_renderer = MapRenderer()
        self.item_icons = ItemIconCache()
        self.avatars = SteamAvatarCache()
        self.player_intel = self.connection._player_intel
        self._wire_events()
        self._auto_connect_timer: Optional[threading.Timer] = None
        self._hotkey_handles: list = []

    def _wire_events(self) -> None:
        self.event_bus.subscribe(EventType.SERVER_PAIRED, self._on_server_paired)
        self.event_bus.subscribe(EventType.DEVICE_PAIRED, self._on_device_paired)
        self.event_bus.subscribe(EventType.TEAM_INFO, self._on_team_info)

    def _on_team_info(self, event) -> None:
        for member in event.payload.get("members", []):
            steam_id = member.get("steam_id")
            if not steam_id:
                continue
            sid = int(steam_id)

            def on_ready(ready_sid: int, img) -> None:
                self.map_renderer.set_avatar(ready_sid, img)

            self.avatars.fetch_async(sid, on_ready)

    def _on_server_paired(self, event) -> None:
        ip = str(event.payload["ip"])
        port = int(event.payload["port"])
        player_id = int(event.payload["player_id"])
        player_token = int(event.payload["player_token"])
        name = str(event.payload.get("name", "Server"))

        existing = None
        for server in self.store.list_servers():
            if server.ip == ip and server.port == port and server.player_id == player_id:
                existing = server
                break

        server = self.store.add_server(name, ip, port, player_id, player_token)
        self.store.set_active_server_id(server.id)

        if existing:
            status = (
                f"Сервер обновлён: {server.name}\n"
                f"{server.ip}:{server.port}, новый token ...{str(server.player_token)[-4:]}\n"
                "Автоподключение через 2 сек..."
            )
        else:
            status = (
                f"Новый сервер: {server.name}\n"
                f"{server.ip}:{server.port}, token ...{str(server.player_token)[-4:]}\n"
                "Автоподключение через 2 сек..."
            )
        self.event_bus.emit(EventType.STATUS, message=status, server_id=server.id)
        self._schedule_auto_connect(server)

    def _schedule_auto_connect(self, server: PairedServer) -> None:
        if self._auto_connect_timer:
            self._auto_connect_timer.cancel()

        def connect():
            self.connect_server(server)

        self._auto_connect_timer = threading.Timer(2.0, connect)
        self._auto_connect_timer.daemon = True
        self._auto_connect_timer.start()

    def _on_device_paired(self, event) -> None:
        server_id = self.store.get_active_server_id()
        if not server_id and self.store.list_servers():
            server_id = self.store.list_servers()[-1].id
        if not server_id:
            self.event_bus.emit(EventType.ERROR, message="Устройство спарено, но нет активного сервера")
            return

        device = self.store.add_device(
            server_id=server_id,
            entity_id=int(event.payload["entity_id"]),
            name=str(event.payload.get("name", "Device")),
            device_type=str(event.payload.get("device_type", "smart_switch")),
        )
        self.event_bus.emit(
            EventType.STATUS,
            message=f"Устройство добавлено: {device.name}",
            device_id=device.id,
        )
        if self.connection.is_connected:
            self.connection.refresh_devices()
            self.refresh_device_states()

    def start(self) -> None:
        self.connection.start()
        self.reload_device_hotkeys()
        self.item_icons.refresh_catalog_async()
        if self.store.has_fcm_config() and self.fcm.runtime_ready():
            self.fcm.start_listen()
        self._restore_last_connection()

    def _restore_last_connection(self) -> None:
        """При старте сразу подключаемся к серверу, который был активен при выходе."""
        if self.connection.is_connected:
            return
        server_id = self.store.get_active_server_id()
        if not server_id:
            return
        server = self.store.get_server(server_id)
        if not server:
            return
        self.event_bus.emit(
            EventType.STATUS,
            message=f"Автоподключение к {server.name}…",
            server_id=server.id,
        )
        self.connect_server(server)
    def stop(self) -> None:
        if self._auto_connect_timer:
            self._auto_connect_timer.cancel()
            self._auto_connect_timer = None
        self.unload_device_hotkeys()
        self.connection.stop()
        self.fcm.stop_all()

    def reload_device_hotkeys(self) -> None:
        self.unload_device_hotkeys()
        for entry in self.store.list_device_hotkeys():
            if not entry.hotkey:
                continue
            try:
                if entry.group_id:
                    handle = add_hotkey_precise(
                        entry.hotkey,
                        lambda gid=entry.group_id, act=entry.action: self.connection.toggle_group(gid, act),
                        suppress=False,
                    )
                elif entry.device_id:
                    device = next((d for d in self.store.list_devices() if d.id == entry.device_id), None)
                    if not device:
                        continue
                    handle = add_hotkey_precise(
                        entry.hotkey,
                        lambda eid=device.entity_id, act=entry.action: self.connection.toggle_entity(eid, act),
                        suppress=False,
                    )
                else:
                    continue
                self._hotkey_handles.append(handle)
            except Exception:
                continue

    def unload_device_hotkeys(self) -> None:
        import keyboard

        for handle in self._hotkey_handles:
            try:
                keyboard.remove_hotkey(handle)
            except Exception:
                pass
        self._hotkey_handles.clear()

    def remove_server(self, server_id: str) -> None:
        if self._auto_connect_timer:
            self._auto_connect_timer.cancel()
            self._auto_connect_timer = None
        if self.connection.connected_server and self.connection.connected_server.id == server_id:
            self.disconnect_server()
        for device in self.store.list_devices(server_id):
            self.store.remove_device(device.id)
        for camera in self.store.list_cameras(server_id):
            self.store.remove_camera(camera.id)
        self.store.remove_server(server_id)

    def connect_server(self, server: PairedServer) -> None:
        self.connection.connect(server)

    def disconnect_server(self) -> None:
        if self._auto_connect_timer:
            self._auto_connect_timer.cancel()
            self._auto_connect_timer = None
        self.connection.disconnect()
        self.store.set_active_server_id(None)

    def fetch_map(self) -> None:
        self.connection.fetch_map()

    def toggle_device(self, entity_id: int, value: bool) -> None:
        self.connection.set_entity_value(entity_id, value)

    def refresh_device_states(self) -> None:
        self.connection.refresh_device_states()

    def open_camera(self, camera_id: str) -> None:
        self.connection.open_camera(camera_id)

    def close_camera(self) -> None:
        self.connection.close_camera()

    def camera_move(self, *movements: int) -> None:
        self.connection.camera_send_movement(list(movements))

    def camera_clear_movement(self) -> None:
        self.connection.camera_send_movement([])

    def camera_look(self, dx: float, dy: float) -> None:
        self.connection.camera_send_look(dx, dy)

    def add_camera(self, camera_id: str, name: Optional[str] = None) -> None:
        server = self.get_active_server()
        if not server:
            self.event_bus.emit(EventType.ERROR, message="Нет активного сервера для камеры")
            return
        camera = self.store.add_camera(server.id, camera_id, name)
        self.event_bus.emit(EventType.STATUS, message=f"Камера добавлена: {camera.name}")

    def remove_camera(self, camera_db_id: str) -> None:
        self.store.remove_camera(camera_db_id)

    def get_active_server(self) -> Optional[PairedServer]:
        server_id = self.store.get_active_server_id()
        if server_id:
            return self.store.get_server(server_id)
        servers = self.store.list_servers()
        return servers[0] if servers else None

    def update_alert_settings(self, alerts: AlertSettings) -> None:
        self.store.set_alert_settings(alerts)

    def update_map_layers(self, layers: MapLayerSettings) -> None:
        self.store.set_map_layers(layers)

    def update_app_settings(self, settings: AppSettings) -> None:
        self.store.set_settings(settings)

    def profit_trades(self, item_id: int):
        from services.rustplus.shop_tracker import ShopTracker

        vendors = self.connection.markers_cache.get("vendors", [])
        return ShopTracker().profit_trades(vendors, item_id)

    def profit_trades_all(self, *, limit: int = 30):
        from services.rustplus.shop_tracker import ShopTracker

        vendors = self.connection.markers_cache.get("vendors", [])
        return ShopTracker().profit_trades_all(vendors, limit=limit)

    def list_shop_watch_items(self, server_id: Optional[str] = None) -> list[int]:
        return self.store.list_shop_watch_items(server_id)

    def add_shop_watch_item(self, item_id: int) -> list[int]:
        server = self.get_active_server()
        if not server:
            self.event_bus.emit(EventType.ERROR, message="Watchlist: нет активного сервера")
            return []
        return self.store.add_shop_watch_item(server.id, int(item_id))

    def remove_shop_watch_item(self, item_id: int) -> list[int]:
        server = self.get_active_server()
        if not server:
            self.event_bus.emit(EventType.ERROR, message="Watchlist: нет активного сервера")
            return []
        return self.store.remove_shop_watch_item(server.id, int(item_id))

    def predict_online(self, steam_id: int) -> Optional[str]:
        server = self.get_active_server()
        if not server:
            return None
        return self.player_intel.predict_online(server.id, steam_id)

    def heatmap(self, steam_id: int):
        server = self.get_active_server()
        if not server:
            return {}
        return self.player_intel.heatmap(server.id, steam_id)
