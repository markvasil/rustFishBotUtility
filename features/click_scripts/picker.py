from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional

import customtkinter as ctk


class PointPicker:
    """Полноэкранный выбор точки кликом мыши."""

    def __init__(self, root: ctk.CTk) -> None:
        self._root = root
        self._win: Optional[tk.Toplevel] = None
        self._callback: Optional[Callable[[int, int], None]] = None
        self._on_cancel: Optional[Callable[[], None]] = None

    @property
    def is_active(self) -> bool:
        return self._win is not None and self._win.winfo_exists()

    def pick(
        self,
        on_picked: Callable[[int, int], None],
        on_cancel: Optional[Callable[[], None]] = None,
    ) -> None:
        self.cancel()
        self._callback = on_picked
        self._on_cancel = on_cancel

        win = tk.Toplevel(self._root)
        self._win = win
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.35)
        win.configure(bg="#0d1117")

        screen_w = win.winfo_screenwidth()
        screen_h = win.winfo_screenheight()
        win.geometry(f"{screen_w}x{screen_h}+0+0")

        canvas = tk.Canvas(win, bg="#0d1117", highlightthickness=0, cursor="crosshair")
        canvas.pack(fill="both", expand=True)
        canvas.create_text(
            screen_w // 2,
            screen_h // 2,
            text="Кликни по нужной точке экрана\nEsc — отмена",
            fill="#e8ecf4",
            font=("Segoe UI", 22, "bold"),
            justify="center",
        )

        canvas.bind("<Button-1>", self._on_click)
        win.bind("<Escape>", lambda _e: self._cancel())
        win.focus_force()
        win.grab_set()

    def cancel(self) -> None:
        if self._win is not None:
            try:
                self._win.grab_release()
            except Exception:
                pass
            try:
                if self._win.winfo_exists():
                    self._win.destroy()
            except Exception:
                pass
        self._win = None

    def _on_click(self, event: tk.Event) -> None:
        x, y = int(event.x_root), int(event.y_root)
        callback = self._callback
        self._callback = None
        self.cancel()
        if callback:
            callback(x, y)

    def _cancel(self) -> None:
        on_cancel = self._on_cancel
        self._callback = None
        self._on_cancel = None
        self.cancel()
        if on_cancel:
            on_cancel()
