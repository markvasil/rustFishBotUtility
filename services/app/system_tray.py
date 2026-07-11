from __future__ import annotations

import threading
from typing import Callable, Optional

import ctypes


class SystemTray:
    """Минимальный Windows tray через ctypes (без pystray)."""

    WM_USER = 0x0400
    WM_TRAY = WM_USER + 1
    NIM_ADD = 0x00000000
    NIM_MODIFY = 0x00000001
    NIM_DELETE = 0x00000002
    NIF_MESSAGE = 0x00000001
    NIF_ICON = 0x00000002
    NIF_TIP = 0x00000004
    WM_LBUTTONUP = 0x0202
    WM_RBUTTONUP = 0x0205
    WM_QUIT = 0x0012

    def __init__(
        self,
        hwnd: int,
        *,
        on_show: Callable[[], None],
        on_quit: Callable[[], None],
        tooltip: str = "Rust Utility Overlay",
    ) -> None:
        self._hwnd = hwnd
        self._on_show = on_show
        self._on_quit = on_quit
        self._tooltip = tooltip
        self._icon_id = 1
        self._added = False
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._added:
            self._notify(self.NIM_DELETE)
            self._added = False
        user32 = ctypes.windll.user32
        user32.PostMessageW(self._hwnd, self.WM_QUIT, 0, 0)

    def _loop(self) -> None:
        user32 = ctypes.windll.user32
        self._notify(self.NIM_ADD)
        self._added = True

        msg = ctypes.wintypes.MSG()
        while self._running:
            if user32.GetMessageW(ctypes.byref(msg), self._hwnd, 0, 0) > 0:
                if msg.message == self.WM_TRAY:
                    if msg.lParam in (self.WM_LBUTTONUP,):
                        self._on_show()
                    elif msg.lParam == self.WM_RBUTTONUP:
                        self._on_quit()
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            else:
                break

    def _notify(self, action: int) -> None:
        class NOTIFYICONDATAW(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_ulong),
                ("hWnd", ctypes.c_void_p),
                ("uID", ctypes.c_uint),
                ("uFlags", ctypes.c_uint),
                ("uCallbackMessage", ctypes.c_uint),
                ("hIcon", ctypes.c_void_p),
                ("szTip", ctypes.c_wchar * 128),
            ]

        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self._hwnd
        nid.uID = self._icon_id
        nid.uFlags = self.NIF_MESSAGE | self.NIF_TIP
        nid.uCallbackMessage = self.WM_TRAY
        nid.szTip = self._tooltip[:127]
        shell32 = ctypes.windll.shell32
        shell32.Shell_NotifyIconW(action, ctypes.byref(nid))
