from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from app_paths import get_session_path


class SessionStore:
    """Локальное хранилище данных между запусками."""

    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            path = get_session_path()
        self._path = path
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

    def get_feature(self, feature_id: str) -> Dict[str, Any]:
        features = self._data.setdefault("features", {})
        value = features.get(feature_id)
        if isinstance(value, dict):
            return value
        return {}

    def set_feature(self, feature_id: str, payload: Dict[str, Any]) -> None:
        self._data.setdefault("features", {})[feature_id] = payload
        self.save()

    def update_feature(self, feature_id: str, **kwargs: Any) -> None:
        current = self.get_feature(feature_id)
        current.update(kwargs)
        self.set_feature(feature_id, current)
