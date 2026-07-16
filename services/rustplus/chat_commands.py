from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional

from services.rustplus.live_format import world_to_grid
from storage.rustplus_store import PairedDevice, RustPlusStore


class ChatCommandHandler:
    """Обработка team chat команд: !on/!off/!toggle, !leader, !upkeep, !mark, !import."""

    def __init__(
        self,
        store: RustPlusStore,
        *,
        send_message: Callable[[str], None],
        set_entity: Callable[[int, bool], None],
        get_entity_info: Callable[[int], Any],
        get_server_time_raw: Callable[[], Optional[float]],
        get_team: Callable[[], Dict[str, Any]],
        get_map_size: Callable[[], Optional[int]],
    ) -> None:
        self._store = store
        self._send = send_message
        self._set_entity = set_entity
        self._get_entity_info = get_entity_info
        self._get_server_time_raw = get_server_time_raw
        self._get_team = get_team
        self._get_map_size = get_map_size

    def handle(self, name: str, message: str, steam_id: Optional[int] = None) -> bool:
        if not self._store.get_settings().chat_commands_enabled:
            return False

        text = str(message or "").strip()
        if not text.startswith("!"):
            if text.startswith("@@DRAW:"):
                self._import_shared_drawing(text[7:])
                return True
            if text.startswith("@@DEVICES:"):
                self._import_devices(text[10:])
                return True
            return False

        parts = text[1:].split()
        if not parts:
            return False
        cmd = parts[0].lower()
        arg = " ".join(parts[1:]).strip()

        handlers = {
            "on": lambda: self._switch_command(True, arg),
            "off": lambda: self._switch_command(False, arg),
            "toggle": lambda: self._toggle_command(arg),
            "leader": self._leader_command,
            "upkeep": self._upkeep_command,
            "mark": lambda: self._mark_command(name, arg, steam_id),
            "share": self._share_devices_command,
            "import": lambda: self._import_devices(arg),
        }
        handler = handlers.get(cmd)
        if not handler:
            return False
        handler()
        return True

    def _active_server_id(self) -> Optional[str]:
        return self._store.get_active_server_id()

    def _switches(self, name_filter: str = "") -> List[PairedDevice]:
        server_id = self._active_server_id()
        if not server_id:
            return []
        devices = [
            d for d in self._store.list_devices(server_id)
            if d.device_type == "smart_switch"
        ]
        if not name_filter:
            return devices
        filt = name_filter.lower()
        matched = [d for d in devices if filt in d.name.lower()]
        return matched or devices[:1]

    def _switch_command(self, value: bool, name_filter: str) -> None:
        devices = self._switches(name_filter)
        if not devices:
            self._send("!on/!off: нет Smart Switch")
            return
        for device in devices:
            self._set_entity(device.entity_id, value)
        state = "ON" if value else "OFF"
        names = ", ".join(d.name for d in devices[:3])
        self._send(f"Switch {state}: {names}")

    def _toggle_command(self, name_filter: str) -> None:
        devices = self._switches(name_filter)
        if not devices:
            self._send("!toggle: нет Smart Switch")
            return
        for device in devices:
            info = self._get_entity_info(device.entity_id)
            current = bool(getattr(info, "value", False)) if info else False
            self._set_entity(device.entity_id, not current)
        names = ", ".join(d.name for d in devices[:3])
        self._send(f"Switch toggle: {names}")

    def _leader_command(self) -> None:
        team = self._get_team()
        leader_id = team.get("leader_steam_id")
        members = team.get("members", [])
        leader = next((m for m in members if m.get("steam_id") == leader_id), None)
        if not leader:
            self._send("!leader: лидер не найден")
            return
        grid = leader.get("grid", "?")
        online = "онлайн" if leader.get("is_online") else "оффлайн"
        self._send(f"Лидер: {leader.get('name', '?')} [{grid}] — {online}")

    def _upkeep_command(self) -> None:
        server_id = self._active_server_id()
        if not server_id:
            self._send("!upkeep: нет сервера")
            return
        monitors = [
            d for d in self._store.list_devices(server_id)
            if d.device_type == "storage_monitor"
        ]
        if not monitors:
            self._send("!upkeep: нет Storage Monitor")
            return

        raw_time = self._get_server_time_raw()
        lines: List[str] = []
        for device in monitors:
            info = self._get_entity_info(device.entity_id)
            if not info:
                lines.append(f"{device.name}: нет данных")
                continue
            expiry = getattr(info, "protection_expiry", 0)
            if not getattr(info, "has_protection", False) or not expiry or raw_time is None:
                lines.append(f"{device.name}: upkeep н/д")
                continue
            hours = max(0.0, (float(expiry) - float(raw_time)) / 3600.0)
            if hours < 1:
                lines.append(f"{device.name}: {hours * 60:.0f} мин ⚠")
            else:
                lines.append(f"{device.name}: {hours:.1f} ч")
        self._send("Upkeep: " + " | ".join(lines[:4]))

    def _mark_command(self, author: str, arg: str, steam_id: Optional[int]) -> None:
        if not arg:
            self._send("!mark <текст> — метка на вашей позиции")
            return
        team = self._get_team()
        member = None
        if steam_id:
            member = next((m for m in team.get("members", []) if m.get("steam_id") == steam_id), None)
        if not member:
            member = next((m for m in team.get("members", []) if m.get("name") == author), None)
        if not member or member.get("x") is None:
            self._send("!mark: позиция недоступна")
            return
        server_id = self._active_server_id()
        if not server_id:
            return
        drawing = self._store.add_map_drawing(
            server_id=server_id,
            x=float(member["x"]),
            y=float(member["y"]),
            text=arg,
            color="#fbbf24",
            author=author,
        )
        payload = json.dumps(
            {"x": drawing.x, "y": drawing.y, "text": drawing.text, "color": drawing.color},
            ensure_ascii=False,
        )
        self._send(f"@@DRAW:{payload}")

    def _share_devices_command(self) -> None:
        server_id = self._active_server_id()
        if not server_id:
            self._send("!share: нет сервера")
            return
        blob = self._store.export_devices(server_id)
        if len(blob) > 400:
            self._send("!share: слишком много устройств для чата")
            return
        self._send(f"@@DEVICES:{blob}")

    def _import_shared_drawing(self, payload: str) -> None:
        server_id = self._active_server_id()
        if not server_id:
            return
        try:
            data = json.loads(payload)
            self._store.add_map_drawing(
                server_id=server_id,
                x=float(data["x"]),
                y=float(data["y"]),
                text=str(data.get("text", "")),
                color=str(data.get("color", "#fbbf24")),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            pass

    def _import_devices(self, payload: str) -> None:
        server_id = self._active_server_id()
        if not server_id or not payload:
            self._send("!import: пустые данные")
            return
        count = self._store.import_devices(server_id, payload)
        self._send(f"Импорт устройств: +{count}")
