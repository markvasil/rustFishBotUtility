from __future__ import annotations

import queue
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional


class EventType(str, Enum):
    STATUS = "status"
    ERROR = "error"
    SERVER_PAIRED = "server_paired"
    DEVICE_PAIRED = "device_paired"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    SERVER_INFO = "server_info"
    TEAM_INFO = "team_info"
    CHAT_MESSAGE = "chat_message"
    MARKERS = "markers"
    ENTITY_CHANGED = "entity_changed"
    MAP_IMAGE = "map_image"
    SERVER_TIME = "server_time"
    LIVE_ALERT = "live_alert"
    CAMERA_FRAME = "camera_frame"
    CAMERA_STATUS = "camera_status"


@dataclass
class RustPlusEvent:
    type: EventType
    payload: Dict[str, Any]


class EventBus:
    """Потокобезопасная шина событий Rust+ → Tkinter через root.after."""

    def __init__(self) -> None:
        self._queue: queue.Queue[RustPlusEvent] = queue.Queue()
        self._handlers: Dict[EventType, list[Callable[[RustPlusEvent], None]]] = {}

    def emit(self, event_type: EventType, **payload: Any) -> None:
        self._queue.put(RustPlusEvent(type=event_type, payload=payload))

    def subscribe(self, event_type: EventType, handler: Callable[[RustPlusEvent], None]) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    def poll(self) -> list[RustPlusEvent]:
        events: list[RustPlusEvent] = []
        while True:
            try:
                events.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return events

    def dispatch(self, event: RustPlusEvent) -> None:
        for handler in self._handlers.get(event.type, []):
            try:
                handler(event)
            except Exception:
                pass

    def dispatch_all_pending(self) -> None:
        for event in self.poll():
            self.dispatch(event)
