from __future__ import annotations

import os
import sys
from pathlib import Path


def get_user_data_dir() -> Path:
    """Папка пользовательских данных (сессия, настройки)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path.home() / ".local" / "share"
    path = base / "RustUtilityOverlay"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_session_path() -> Path:
    return get_user_data_dir() / "session.json"


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)
