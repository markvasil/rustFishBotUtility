from __future__ import annotations

import threading
import winsound
from pathlib import Path
from typing import Optional

from storage.rustplus_store import AlertSettings, RustPlusStore


class AlertManager:
    """Фильтрация алертов и кастомный звук Smart Alarm."""

    def __init__(self, store: RustPlusStore) -> None:
        self._store = store
        self._lock = threading.Lock()

    @property
    def settings(self) -> AlertSettings:
        return self._store.get_alert_settings()

    def should_emit(self, category: str) -> bool:
        s = self.settings
        mapping = {
            "cargo": s.cargo,
            "death": s.death,
            "shop": s.shop,
            "alarm": s.alarm,
            "event": s.cargo,
            "spawn_patrol": s.spawn_patrol,
            "spawn_chinook": s.spawn_chinook,
            "spawn_cargo": s.spawn_cargo,
            "spawn_vendor": s.spawn_vendor,
        }
        return mapping.get(category, True)

    def play_alarm(self) -> None:
        path = self._store.get_settings().alarm_sound_path
        if path and Path(path).exists():
            try:
                winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
                return
            except Exception:
                pass
        try:
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass
