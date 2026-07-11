from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional

import customtkinter as ctk

from storage.rustplus_store import AppSettings


class CrosshairWindow:
    """Прозрачный оверлей прицела поверх игры."""

    def __init__(self, root: ctk.CTk, get_settings: Callable[[], AppSettings]) -> None:
        self._root = root
        self._get_settings = get_settings
        self._win: Optional[tk.Toplevel] = None
        self._canvas: Optional[tk.Canvas] = None
        self._visible = False

    @property
    def is_visible(self) -> bool:
        return self._visible and self._win is not None and self._win.winfo_exists()

    def apply_settings(self) -> None:
        settings = self._get_settings()
        if settings.crosshair_enabled:
            self.show()
        else:
            self.hide()
        self._redraw()

    def show(self) -> None:
        settings = self._get_settings()
        if not settings.crosshair_enabled:
            return
        if self._win is None or not self._win.winfo_exists():
            self._win = tk.Toplevel(self._root)
            self._win.overrideredirect(True)
            self._win.attributes("-topmost", True)
            self._win.attributes("-transparentcolor", "#010101")
            self._win.configure(bg="#010101")
            sw = self._root.winfo_screenwidth()
            sh = self._root.winfo_screenheight()
            self._win.geometry(f"{sw}x{sh}+0+0")
            self._canvas = tk.Canvas(self._win, bg="#010101", highlightthickness=0, bd=0)
            self._canvas.pack(fill="both", expand=True)
        self._win.deiconify()
        self._visible = True
        self._redraw()

    def hide(self) -> None:
        self._visible = False
        if self._win and self._win.winfo_exists():
            self._win.withdraw()

    def destroy(self) -> None:
        self._visible = False
        if self._win and self._win.winfo_exists():
            self._win.destroy()
        self._win = None
        self._canvas = None

    def _redraw(self) -> None:
        if not self._canvas or not self.is_visible:
            return
        settings = self._get_settings()
        self._canvas.delete("all")
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        cx, cy = sw // 2, sh // 2
        size = max(2, settings.crosshair_size)
        gap = max(0, settings.crosshair_gap)
        thick = max(1, settings.crosshair_thickness)
        color = settings.crosshair_color
        self._canvas.create_line(cx, cy - gap - size, cx, cy - gap, fill=color, width=thick)
        self._canvas.create_line(cx, cy + gap, cx, cy + gap + size, fill=color, width=thick)
        self._canvas.create_line(cx - gap - size, cy, cx - gap, cy, fill=color, width=thick)
        self._canvas.create_line(cx + gap, cy, cx + gap + size, cy, fill=color, width=thick)
