"""Захват горячей клавиши нажатием (без ручного ввода имени)."""

from __future__ import annotations

from typing import Callable, Optional, Set

import customtkinter as ctk
import keyboard

from overlay.hotkey_util import current_modifiers, event_to_hotkey

_MODIFIERS: Set[str] = {
    "ctrl",
    "alt",
    "shift",
    "left ctrl",
    "right ctrl",
    "left alt",
    "right alt",
    "left shift",
    "right shift",
    "windows",
    "left windows",
    "right windows",
    "cmd",
    "alt gr",
}


class KeyCapture:
    """Полноэкранный оверлей: нажатие → точная hotkey-строка (sc: для numpad)."""

    def __init__(self, root: ctk.CTk) -> None:
        self._root = root
        self._win: Optional[ctk.CTkToplevel] = None
        self._hook = None
        self._callback: Optional[Callable[[str], None]] = None
        self._on_cancel: Optional[Callable[[], None]] = None
        self._done = False

    @property
    def is_active(self) -> bool:
        return self._win is not None and self._win.winfo_exists()

    def capture(
        self,
        on_captured: Callable[[str], None],
        *,
        on_cancel: Optional[Callable[[], None]] = None,
        prompt: str = "Нажмите клавишу для привязки",
    ) -> None:
        self.cancel()
        self._done = False
        self._callback = on_captured
        self._on_cancel = on_cancel

        win = ctk.CTkToplevel(self._root)
        self._win = win
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.92)
        win.configure(fg_color="#0d1117")

        screen_w = self._root.winfo_screenwidth()
        screen_h = self._root.winfo_screenheight()
        win.geometry(f"{screen_w}x{screen_h}+0+0")

        card = ctk.CTkFrame(
            win,
            fg_color="#141a28",
            corner_radius=16,
            border_width=1,
            border_color="#2a3348",
            width=440,
            height=170,
        )
        card.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            card,
            text=prompt,
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#e8ecf4",
        ).pack(pady=(36, 8), padx=24)

        ctk.CTkLabel(
            card,
            text="Esc — отмена · нумпад сохраняется отдельно от ряда цифр",
            font=ctk.CTkFont(size=12),
            text_color="#8b93a7",
        ).pack(pady=(0, 28))

        try:
            win.grab_set()
            win.focus_force()
        except Exception:
            pass

        self._hook = keyboard.hook(self._on_event, suppress=False)

    def cancel(self) -> None:
        was_active = self.is_active and not self._done
        self._done = True
        self._teardown()
        if was_active and self._on_cancel:
            cb = self._on_cancel
            self._on_cancel = None
            self._root.after(0, cb)

    def _teardown(self) -> None:
        if self._hook is not None:
            try:
                keyboard.unhook(self._hook)
            except Exception:
                pass
            self._hook = None
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

    def _on_event(self, event) -> None:
        if self._done or getattr(event, "event_type", None) != "down":
            return

        name = str(getattr(event, "name", "") or "").lower().strip()
        if name in _MODIFIERS:
            return
        if name == "esc":
            self._finish_cancel()
            return

        key = name.replace("left ", "").replace("right ", "")
        if key in _MODIFIERS or key in {"ctrl", "alt", "shift", "windows", "cmd"}:
            return

        try:
            hotkey = event_to_hotkey(event, current_modifiers())
        except ValueError:
            return
        self._finish_ok(hotkey)

    def _finish_ok(self, hotkey: str) -> None:
        if self._done:
            return
        self._done = True
        callback = self._callback
        self._callback = None
        self._on_cancel = None
        self._teardown()
        if callback:
            self._root.after(0, lambda: callback(hotkey))

    def _finish_cancel(self) -> None:
        if self._done:
            return
        self._done = True
        on_cancel = self._on_cancel
        self._callback = None
        self._on_cancel = None
        self._teardown()
        if on_cancel:
            self._root.after(0, on_cancel)
