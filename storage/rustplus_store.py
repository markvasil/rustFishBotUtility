from __future__ import annotations

import base64
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from app_paths import get_fcm_config_path, get_rustplus_data_path


@dataclass
class PairedServer:
    id: str
    name: str
    ip: str
    port: int
    player_id: int
    player_token: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PairedServer:
        return cls(
            id=str(data["id"]),
            name=str(data.get("name", "Server")),
            ip=str(data["ip"]),
            port=int(data["port"]),
            player_id=int(data["player_id"]),
            player_token=int(data["player_token"]),
        )


@dataclass
class PairedCamera:
    id: str
    server_id: str
    camera_id: str
    name: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PairedCamera:
        return cls(
            id=str(data["id"]),
            server_id=str(data["server_id"]),
            camera_id=str(data["camera_id"]),
            name=str(data.get("name", data.get("camera_id", "Camera"))),
        )


@dataclass
class AlertSettings:
    cargo: bool = True
    death: bool = True
    shop: bool = True
    alarm: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AlertSettings:
        return cls(
            cargo=bool(data.get("cargo", True)),
            death=bool(data.get("death", True)),
            shop=bool(data.get("shop", True)),
            alarm=bool(data.get("alarm", True)),
        )


@dataclass
class AppSettings:
    alerts: AlertSettings = field(default_factory=AlertSettings)
    autostart: bool = False
    minimize_to_tray: bool = True
    alarm_sound_path: str = ""
    follow_steam_id: Optional[int] = None
    chat_commands_enabled: bool = True
    fcm_registered_at: Optional[int] = None
    crosshair_enabled: bool = False
    crosshair_size: int = 8
    crosshair_gap: int = 4
    crosshair_thickness: int = 2
    crosshair_color: str = "#00ff00"
    tracked_event_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["alerts"] = self.alerts.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AppSettings:
        alerts = AlertSettings.from_dict(data.get("alerts", {}))
        return cls(
            alerts=alerts,
            autostart=bool(data.get("autostart", False)),
            minimize_to_tray=bool(data.get("minimize_to_tray", True)),
            alarm_sound_path=str(data.get("alarm_sound_path", "")),
            follow_steam_id=int(data["follow_steam_id"]) if data.get("follow_steam_id") else None,
            chat_commands_enabled=bool(data.get("chat_commands_enabled", True)),
            fcm_registered_at=int(data["fcm_registered_at"]) if data.get("fcm_registered_at") else None,
            crosshair_enabled=bool(data.get("crosshair_enabled", False)),
            crosshair_size=int(data.get("crosshair_size", 8)),
            crosshair_gap=int(data.get("crosshair_gap", 4)),
            crosshair_thickness=int(data.get("crosshair_thickness", 2)),
            crosshair_color=str(data.get("crosshair_color", "#00ff00")),
            tracked_event_id=int(data["tracked_event_id"]) if data.get("tracked_event_id") else None,
        )


@dataclass
class DeviceGroup:
    id: str
    server_id: str
    name: str
    device_ids: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DeviceGroup:
        return cls(
            id=str(data["id"]),
            server_id=str(data["server_id"]),
            name=str(data.get("name", "Group")),
            device_ids=[str(x) for x in data.get("device_ids", [])],
        )


@dataclass
class DeviceHotkey:
    id: str
    hotkey: str
    group_id: Optional[str]
    action: str  # on | off | toggle

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DeviceHotkey:
        return cls(
            id=str(data["id"]),
            hotkey=str(data.get("hotkey", "")),
            group_id=str(data["group_id"]) if data.get("group_id") else None,
            action=str(data.get("action", "toggle")),
        )


@dataclass
class DeathMarker:
    server_id: str
    steam_id: int
    name: str
    x: float
    y: float
    grid: str
    ts: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DeathMarker:
        return cls(
            server_id=str(data["server_id"]),
            steam_id=int(data["steam_id"]),
            name=str(data.get("name", "?")),
            x=float(data.get("x", 0)),
            y=float(data.get("y", 0)),
            grid=str(data.get("grid", "?")),
            ts=int(data.get("ts", 0)),
        )


@dataclass
class MapDrawing:
    id: str
    server_id: str
    x: float
    y: float
    text: str
    color: str
    author: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> MapDrawing:
        return cls(
            id=str(data["id"]),
            server_id=str(data["server_id"]),
            x=float(data.get("x", 0)),
            y=float(data.get("y", 0)),
            text=str(data.get("text", "")),
            color=str(data.get("color", "#fbbf24")),
            author=str(data.get("author", "")),
        )


@dataclass
class PairedDevice:
    id: str
    server_id: str
    entity_id: int
    name: str
    device_type: str  # smart_switch | smart_alarm | storage_monitor

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PairedDevice:
        return cls(
            id=str(data["id"]),
            server_id=str(data["server_id"]),
            entity_id=int(data["entity_id"]),
            name=str(data.get("name", "Device")),
            device_type=str(data.get("device_type", "smart_switch")),
        )


class RustPlusStore:
    """Хранилище паринга серверов, устройств и активного подключения."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or get_rustplus_data_path()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._data: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._data = {}
        else:
            self._data = {}

    def save(self) -> None:
        try:
            self._path.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    def has_fcm_config(self) -> bool:
        return get_fcm_config_path().exists()

    def list_servers(self) -> List[PairedServer]:
        return [PairedServer.from_dict(item) for item in self._data.get("servers", [])]

    def get_server(self, server_id: str) -> Optional[PairedServer]:
        for server in self.list_servers():
            if server.id == server_id:
                return server
        return None

    def add_server(self, name: str, ip: str, port: int, player_id: int, player_token: int) -> PairedServer:
        servers = self.list_servers()
        for existing in servers:
            if (
                existing.ip == ip
                and existing.port == port
                and existing.player_id == player_id
            ):
                existing.name = name
                existing.player_token = player_token
                self._set_servers(servers)
                return existing

        server = PairedServer(
            id=str(uuid.uuid4()),
            name=name,
            ip=ip,
            port=port,
            player_id=player_id,
            player_token=player_token,
        )
        servers.append(server)
        self._set_servers(servers)
        return server

    def remove_server(self, server_id: str) -> None:
        servers = [s for s in self.list_servers() if s.id != server_id]
        self._set_servers(servers)
        if self.get_active_server_id() == server_id:
            self.set_active_server_id(None)

    def _set_servers(self, servers: List[PairedServer]) -> None:
        self._data["servers"] = [s.to_dict() for s in servers]
        self.save()

    def get_active_server_id(self) -> Optional[str]:
        value = self._data.get("active_server_id")
        return str(value) if value else None

    def set_active_server_id(self, server_id: Optional[str]) -> None:
        if server_id:
            self._data["active_server_id"] = server_id
        else:
            self._data.pop("active_server_id", None)
        self.save()

    def get_minimap_position(self) -> tuple[Optional[int], Optional[int]]:
        pos = self._data.get("minimap_position", {})
        if not isinstance(pos, dict):
            return None, None
        x, y = pos.get("x"), pos.get("y")
        return (int(x) if x is not None else None, int(y) if y is not None else None)

    def set_minimap_position(self, x: int, y: int) -> None:
        self._data["minimap_position"] = {"x": int(x), "y": int(y)}
        self.save()

    def list_devices(self, server_id: Optional[str] = None) -> List[PairedDevice]:
        devices = [PairedDevice.from_dict(item) for item in self._data.get("devices", [])]
        if server_id:
            return [d for d in devices if d.server_id == server_id]
        return devices

    def add_device(
        self,
        server_id: str,
        entity_id: int,
        name: str,
        device_type: str,
    ) -> PairedDevice:
        devices = self.list_devices()
        for existing in devices:
            if existing.server_id == server_id and existing.entity_id == entity_id:
                existing.name = name
                existing.device_type = device_type
                self._set_devices(devices)
                return existing

        device = PairedDevice(
            id=str(uuid.uuid4()),
            server_id=server_id,
            entity_id=entity_id,
            name=name,
            device_type=device_type,
        )
        devices.append(device)
        self._set_devices(devices)
        return device

    def remove_device(self, device_id: str) -> None:
        devices = [d for d in self.list_devices() if d.id != device_id]
        self._set_devices(devices)

    def list_cameras(self, server_id: Optional[str] = None) -> List[PairedCamera]:
        cameras = [PairedCamera.from_dict(item) for item in self._data.get("cameras", [])]
        if server_id:
            return [c for c in cameras if c.server_id == server_id]
        return cameras

    def add_camera(self, server_id: str, camera_id: str, name: Optional[str] = None) -> PairedCamera:
        camera_id = camera_id.strip().upper()
        cameras = self.list_cameras()
        for existing in cameras:
            if existing.server_id == server_id and existing.camera_id == camera_id:
                if name:
                    existing.name = name
                    self._set_cameras(cameras)
                return existing

        camera = PairedCamera(
            id=str(uuid.uuid4()),
            server_id=server_id,
            camera_id=camera_id,
            name=name or camera_id,
        )
        cameras.append(camera)
        self._set_cameras(cameras)
        return camera

    def remove_camera(self, camera_id: str) -> None:
        cameras = [c for c in self.list_cameras() if c.id != camera_id]
        self._set_cameras(cameras)

    def _set_cameras(self, cameras: List[PairedCamera]) -> None:
        self._data["cameras"] = [c.to_dict() for c in cameras]
        self.save()

    def _set_devices(self, devices: List[PairedDevice]) -> None:
        self._data["devices"] = [d.to_dict() for d in devices]
        self.save()

    def get_settings(self) -> AppSettings:
        raw = self._data.get("settings", {})
        if not isinstance(raw, dict):
            return AppSettings()
        return AppSettings.from_dict(raw)

    def set_settings(self, settings: AppSettings) -> None:
        self._data["settings"] = settings.to_dict()
        self.save()

    def get_alert_settings(self) -> AlertSettings:
        return self.get_settings().alerts

    def set_alert_settings(self, alerts: AlertSettings) -> None:
        settings = self.get_settings()
        settings.alerts = alerts
        self.set_settings(settings)

    def list_device_groups(self, server_id: Optional[str] = None) -> List[DeviceGroup]:
        groups = [DeviceGroup.from_dict(item) for item in self._data.get("device_groups", [])]
        if server_id:
            return [g for g in groups if g.server_id == server_id]
        return groups

    def add_device_group(self, server_id: str, name: str, device_ids: List[str]) -> DeviceGroup:
        groups = self.list_device_groups()
        group = DeviceGroup(id=str(uuid.uuid4()), server_id=server_id, name=name, device_ids=device_ids)
        groups.append(group)
        self._data["device_groups"] = [g.to_dict() for g in groups]
        self.save()
        return group

    def remove_device_group(self, group_id: str) -> None:
        groups = [g for g in self.list_device_groups() if g.id != group_id]
        self._data["device_groups"] = [g.to_dict() for g in groups]
        self.save()

    def list_device_hotkeys(self) -> List[DeviceHotkey]:
        return [DeviceHotkey.from_dict(item) for item in self._data.get("device_hotkeys", [])]

    def add_device_hotkey(self, hotkey: str, group_id: str, action: str = "toggle") -> DeviceHotkey:
        hotkeys = self.list_device_hotkeys()
        entry = DeviceHotkey(id=str(uuid.uuid4()), hotkey=hotkey.lower(), group_id=group_id, action=action)
        hotkeys.append(entry)
        self._data["device_hotkeys"] = [h.to_dict() for h in hotkeys]
        self.save()
        return entry

    def remove_device_hotkey(self, hotkey_id: str) -> None:
        hotkeys = [h for h in self.list_device_hotkeys() if h.id != hotkey_id]
        self._data["device_hotkeys"] = [h.to_dict() for h in hotkeys]
        self.save()

    def list_death_markers(self, server_id: Optional[str] = None) -> List[DeathMarker]:
        markers = [DeathMarker.from_dict(item) for item in self._data.get("death_markers", [])]
        if server_id:
            return [m for m in markers if m.server_id == server_id]
        return markers

    def add_death_marker(self, server_id: str, member: Dict[str, Any]) -> DeathMarker:
        marker = DeathMarker(
            server_id=server_id,
            steam_id=int(member.get("steam_id", 0)),
            name=str(member.get("name", "?")),
            x=float(member.get("x", 0)),
            y=float(member.get("y", 0)),
            grid=str(member.get("grid", "?")),
            ts=int(time.time()),
        )
        markers = self.list_death_markers()
        markers.insert(0, marker)
        self._data["death_markers"] = [m.to_dict() for m in markers[:40]]
        self.save()
        return marker

    def clear_death_markers(self, server_id: Optional[str] = None) -> None:
        if server_id:
            markers = [m for m in self.list_death_markers() if m.server_id != server_id]
        else:
            markers = []
        self._data["death_markers"] = [m.to_dict() for m in markers]
        self.save()

    def list_map_drawings(self, server_id: Optional[str] = None) -> List[MapDrawing]:
        drawings = [MapDrawing.from_dict(item) for item in self._data.get("map_drawings", [])]
        if server_id:
            return [d for d in drawings if d.server_id == server_id]
        return drawings

    def add_map_drawing(
        self,
        server_id: str,
        x: float,
        y: float,
        text: str,
        color: str = "#fbbf24",
        author: str = "",
    ) -> MapDrawing:
        drawing = MapDrawing(
            id=str(uuid.uuid4()),
            server_id=server_id,
            x=x,
            y=y,
            text=text,
            color=color,
            author=author,
        )
        drawings = self.list_map_drawings()
        drawings.insert(0, drawing)
        self._data["map_drawings"] = [d.to_dict() for d in drawings[:60]]
        self.save()
        return drawing

    def remove_map_drawing(self, drawing_id: str) -> None:
        drawings = [d for d in self.list_map_drawings() if d.id != drawing_id]
        self._data["map_drawings"] = [d.to_dict() for d in drawings]
        self.save()

    def set_tracked_event_id(self, event_id: Optional[int]) -> None:
        settings = self.get_settings()
        settings.tracked_event_id = event_id
        self.set_settings(settings)

    def get_tracked_event_id(self) -> Optional[int]:
        return self.get_settings().tracked_event_id

    def set_follow_steam_id(self, steam_id: Optional[int]) -> None:
        settings = self.get_settings()
        settings.follow_steam_id = steam_id
        self.set_settings(settings)

    def get_follow_steam_id(self) -> Optional[int]:
        return self.get_settings().follow_steam_id

    def export_devices(self, server_id: str) -> str:
        payload = [
            {
                "entity_id": d.entity_id,
                "name": d.name,
                "device_type": d.device_type,
            }
            for d in self.list_devices(server_id)
        ]
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return base64.b64encode(raw).decode("ascii")

    def import_devices(self, server_id: str, blob: str) -> int:
        try:
            raw = base64.b64decode(blob.encode("ascii"))
            items = json.loads(raw.decode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            return 0
        if not isinstance(items, list):
            return 0
        added = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                self.add_device(
                    server_id=server_id,
                    entity_id=int(item["entity_id"]),
                    name=str(item.get("name", "Device")),
                    device_type=str(item.get("device_type", "smart_switch")),
                )
                added += 1
            except (KeyError, TypeError, ValueError):
                continue
        return added

    def fcm_expiry_warning(self) -> Optional[str]:
        settings = self.get_settings()
        registered = settings.fcm_registered_at
        if not registered:
            path = get_fcm_config_path()
            if path.exists():
                registered = int(path.stat().st_mtime)
        if not registered:
            return "FCM не зарегистрирован"
        age_days = (int(time.time()) - int(registered)) / 86400
        if age_days >= 25:
            return f"FCM токену ~{age_days:.0f} дней — скоро может потребоваться перерегистрация"
        if age_days >= 14:
            return f"FCM токену {age_days:.0f} дней — проверьте listener"
        return None

    def mark_fcm_registered(self) -> None:
        settings = self.get_settings()
        settings.fcm_registered_at = int(time.time())
        self.set_settings(settings)
