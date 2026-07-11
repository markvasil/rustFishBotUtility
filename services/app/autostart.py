from __future__ import annotations

import os
import sys
import winreg
from typing import Callable, Optional


_APP_NAME = "RustUtilityOverlay"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def is_autostart_enabled() -> bool:
    if sys.platform != "win32":
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, _APP_NAME)
            return True
    except OSError:
        return False


def set_autostart(enabled: bool, executable: Optional[str] = None) -> None:
    if sys.platform != "win32":
        return
    exe = executable or _default_executable()
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE,
        ) as key:
            if enabled:
                winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, f'"{exe}"')
            else:
                try:
                    winreg.DeleteValue(key, _APP_NAME)
                except OSError:
                    pass
    except OSError:
        pass


def _default_executable() -> str:
    if getattr(sys, "frozen", False):
        return sys.executable
    main_py = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "main.py"))
    return f'{sys.executable} "{main_py}"'
