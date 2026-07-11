from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional

import customtkinter as ctk


class Feature(ABC):
    """Базовый класс для вкладок/функций оверлея."""

    id: str
    title: str

    def __init__(self) -> None:
        self._request_resize: Optional[Callable[[], None]] = None

    def set_request_resize(self, callback: Callable[[], None]) -> None:
        self._request_resize = callback

    def request_resize(self) -> None:
        if self._request_resize:
            self._request_resize()

    @abstractmethod
    def build(self, parent: ctk.CTkFrame) -> None:
        """Создаёт UI функции внутри родительского фрейма."""

    def on_show(self) -> None:
        """Вызывается при открытии вкладки."""

    def on_hide(self) -> None:
        """Вызывается при скрытии вкладки."""

    def on_shutdown(self) -> None:
        """Вызывается при завершении приложения."""
