from __future__ import annotations

import ctypes
import sys


_MUTEX_NAME = "RustUtilityOverlay_SingleInstance_v1"


def ensure_single_instance() -> bool:
    """Возвращает False, если уже запущен другой экземпляр."""
    if sys.platform != "win32":
        return True
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, _MUTEX_NAME)
    last_error = kernel32.GetLastError()
    # ERROR_ALREADY_EXISTS = 183
    return last_error != 183
