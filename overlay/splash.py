"""Сплэш при запуске оверлея."""

from __future__ import annotations

from typing import Optional

import customtkinter as ctk


class StartupSplash:
    """Компактный лоадер поверх экрана, пока собирается оверлей."""

    WIDTH = 320
    HEIGHT = 148

    def __init__(self, master: ctk.CTk) -> None:
        self._master = master
        self._window: Optional[ctk.CTkToplevel] = None
        self._status: Optional[ctk.CTkLabel] = None
        self._bar: Optional[ctk.CTkProgressBar] = None
        self._pulse_job: Optional[str] = None
        self._progress = 0.08

    def show(self, status: str = "Запуск…") -> None:
        if self._window is not None and self._window.winfo_exists():
            self.set_status(status)
            return

        win = ctk.CTkToplevel(self._master)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.96)
        win.configure(fg_color="#0d1117")
        win.resizable(False, False)

        screen_w = self._master.winfo_screenwidth()
        screen_h = self._master.winfo_screenheight()
        x = max(0, (screen_w - self.WIDTH) // 2)
        y = max(0, (screen_h - self.HEIGHT) // 2)
        win.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")

        card = ctk.CTkFrame(
            win,
            fg_color="#141a28",
            corner_radius=14,
            border_width=1,
            border_color="#2a3348",
        )
        card.pack(fill="both", expand=True, padx=1, pady=1)

        accent = ctk.CTkFrame(card, fg_color="#e07a3a", height=3, corner_radius=0)
        accent.pack(fill="x", side="top")

        ctk.CTkLabel(
            card,
            text="Rust Utility",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#e8ecf4",
        ).pack(pady=(22, 4))

        self._status = ctk.CTkLabel(
            card,
            text=status,
            font=ctk.CTkFont(size=12),
            text_color="#8b93a7",
        )
        self._status.pack(pady=(0, 14))

        self._bar = ctk.CTkProgressBar(
            card,
            width=220,
            height=8,
            corner_radius=4,
            progress_color="#e07a3a",
            fg_color="#1a2236",
        )
        self._bar.pack(pady=(0, 22))
        self._bar.set(self._progress)

        self._window = win
        self._pulse()
        self._pump()

    def set_status(self, text: str) -> None:
        if self._status is not None and self._status.winfo_exists():
            self._status.configure(text=text)
        self._pump()

    def set_progress(self, value: float) -> None:
        self._progress = max(0.0, min(1.0, value))
        if self._bar is not None and self._bar.winfo_exists():
            self._bar.set(self._progress)
        self._pump()

    def close(self) -> None:
        if self._pulse_job is not None:
            try:
                self._master.after_cancel(self._pulse_job)
            except Exception:
                pass
            self._pulse_job = None
        if self._window is not None:
            try:
                if self._window.winfo_exists():
                    self._window.destroy()
            except Exception:
                pass
            self._window = None
        self._status = None
        self._bar = None

    def _pulse(self) -> None:
        if self._window is None or not self._window.winfo_exists():
            return
        # лёгкая анимация, пока шаги не выставили точный прогресс
        if self._progress < 0.92:
            self._progress = min(0.92, self._progress + 0.012)
            if self._bar is not None and self._bar.winfo_exists():
                self._bar.set(self._progress)
        self._pulse_job = self._master.after(40, self._pulse)

    def _pump(self) -> None:
        try:
            self._master.update_idletasks()
            self._master.update()
        except Exception:
            pass
