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


def get_rustplus_dir() -> Path:
    path = get_user_data_dir() / "rustplus"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_fcm_config_path() -> Path:
    return get_rustplus_dir() / "rustplusjs-config.json"


def get_rustplus_data_path() -> Path:
    return get_rustplus_dir() / "data.json"


def get_runtime_dir() -> Path:
    """Bundled Node + rustplus-cli (как в Rust+ Desktop)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent / "runtime"
    return Path(__file__).resolve().parent / "runtime"


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)
