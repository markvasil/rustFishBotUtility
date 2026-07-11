from __future__ import annotations

from typing import Optional

import customtkinter as ctk


class ToastManager:
    """Короткие уведомления поверх игры (даже когда оверлей скрыт)."""

    def __init__(self, root: ctk.CTk) -> None:
        self._root = root
        self._window: Optional[ctk.CTkToplevel] = None
        self._label: Optional[ctk.CTkLabel] = None
        self._hide_job: Optional[str] = None

    def show(self, message: str, duration_ms: int = 6000) -> None:
        if self._hide_job:
            self._root.after_cancel(self._hide_job)
            self._hide_job = None

        if self._window is None or not self._window.winfo_exists():
            self._window = ctk.CTkToplevel(self._root)
            self._window.overrideredirect(True)
            self._window.attributes("-topmost", True)
            self._window.configure(fg_color="#1a2030")
            frame = ctk.CTkFrame(self._window, fg_color="#1a2030", corner_radius=8)
            frame.pack(padx=2, pady=2)
            self._label = ctk.CTkLabel(
                frame,
                text=message,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#fbbf24",
                wraplength=360,
                justify="left",
            )
            self._label.pack(padx=14, pady=10)

        assert self._label is not None
        assert self._window is not None
        self._label.configure(text=message)
        self._window.update_idletasks()

        screen_w = self._root.winfo_screenwidth()
        screen_h = self._root.winfo_screenheight()
        width = max(280, self._window.winfo_reqwidth())
        height = self._window.winfo_reqheight()
        x = screen_w - width - 24
        y = screen_h - height - 80
        self._window.geometry(f"{width}x{height}+{x}+{y}")
        self._window.deiconify()
        self._window.lift()

        self._hide_job = self._root.after(duration_ms, self._hide)

    def _hide(self) -> None:
        self._hide_job = None
        if self._window and self._window.winfo_exists():
            self._window.withdraw()
