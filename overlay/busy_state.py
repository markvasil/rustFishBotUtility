from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, Dict, Iterator, Optional, Set

import customtkinter as ctk


class OperationRegistry:
    """Реестр in-flight операций — не допускает повторный запуск одного action."""

    def __init__(self) -> None:
        self._active: Set[str] = set()

    def is_busy(self, key: str) -> bool:
        return key in self._active

    def release(self, key: str) -> None:
        self._active.discard(key)

    def acquire(self, key: str) -> bool:
        if key in self._active:
            return False
        self._active.add(key)
        return True

    @contextmanager
    def guard(self, key: str) -> Iterator[bool]:
        if key in self._active:
            yield False
            return
        self._active.add(key)
        try:
            yield True
        finally:
            self._active.discard(key)


class BusyButton:
    """Обёртка над CTkButton: disabled + текст «…» на время операции."""

    def __init__(self, button: ctk.CTkButton) -> None:
        self._button = button
        self._default_text = button.cget("text")
        self._busy = False

    @property
    def widget(self) -> ctk.CTkButton:
        return self._button

    @property
    def is_busy(self) -> bool:
        return self._busy

    def set_default_text(self, text: str) -> None:
        self._default_text = text
        if not self._busy:
            self._button.configure(text=text)

    def begin(self, busy_text: Optional[str] = None) -> None:
        self._busy = True
        self._button.configure(state="disabled", text=busy_text or f"{self._default_text}…")

    def end(self) -> None:
        self._busy = False
        self._button.configure(state="normal", text=self._default_text)


class BusyLabel:
    """Маленький статус рядом с секцией (spinner-like текст)."""

    def __init__(self, parent, *, text_color: str = "#6ec1e4") -> None:
        self._label = ctk.CTkLabel(
            parent,
            text="",
            font=ctk.CTkFont(size=10),
            text_color=text_color,
            anchor="w",
        )

    @property
    def widget(self) -> ctk.CTkLabel:
        return self._label

    def pack(self, **kwargs) -> None:
        self._label.pack(**kwargs)

    def pack_forget(self) -> None:
        self._label.pack_forget()

    def set(self, message: str) -> None:
        if message:
            self._label.configure(text=message)
            if not self._label.winfo_ismapped():
                self._label.pack(anchor="w", pady=(2, 0))
        else:
            self.pack_forget()
            self._label.configure(text="")


def run_guarded(
    registry: OperationRegistry,
    key: str,
    *,
    on_begin: Optional[Callable[[], None]] = None,
    on_end: Optional[Callable[[], None]] = None,
    action: Callable[[], None],
) -> bool:
    """Запускает action, если key ещё не занят. Возвращает True если запущено."""
    with registry.guard(key) as acquired:
        if not acquired:
            return False
        if on_begin:
            on_begin()
        try:
            action()
        finally:
            if on_end:
                on_end()
        return True
