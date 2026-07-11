from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


@dataclass
class ActiveTimer:
    id: str
    title: str
    end_time: float
    created_at: float = field(default_factory=time.time)

    @property
    def remaining(self) -> float:
        return max(0.0, self.end_time - time.time())

    def to_dict(self) -> Dict[str, float | str]:
        return {
            "id": self.id,
            "title": self.title,
            "end_time": self.end_time,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> ActiveTimer:
        return cls(
            id=str(data["id"]),
            title=str(data["title"]),
            end_time=float(data["end_time"]),
            created_at=float(data.get("created_at", time.time())),
        )


class TimerManager:
    def __init__(
        self,
        root,
        on_complete: Callable[[ActiveTimer], None],
        on_tick: Optional[Callable[[], None]] = None,
    ) -> None:
        self._root = root
        self._on_complete = on_complete
        self._on_tick = on_tick
        self._timers: Dict[str, ActiveTimer] = {}
        self._running = True
        self._schedule_tick()

    def set_on_tick(self, callback: Callable[[], None]) -> None:
        self._on_tick = callback

    def _schedule_tick(self) -> None:
        if self._running:
            self._root.after(1000, self._tick)

    def _tick(self) -> None:
        completed: List[ActiveTimer] = []
        for timer in list(self._timers.values()):
            if timer.remaining <= 0:
                completed.append(timer)
                del self._timers[timer.id]

        for timer in completed:
            self._on_complete(timer)

        if self._on_tick:
            self._on_tick()

        self._schedule_tick()

    def add(self, title: str, duration_seconds: float) -> ActiveTimer:
        timer = ActiveTimer(
            id=str(uuid.uuid4()),
            title=title,
            end_time=time.time() + duration_seconds,
        )
        self._timers[timer.id] = timer
        return timer

    def remove(self, timer_id: str) -> None:
        self._timers.pop(timer_id, None)

    def clear(self) -> None:
        self._timers.clear()

    def list_active(self) -> List[ActiveTimer]:
        return sorted(self._timers.values(), key=lambda t: t.end_time)

    def load(self, items: List[Dict]) -> None:
        self._timers.clear()
        now = time.time()
        for raw in items:
            timer = ActiveTimer.from_dict(raw)
            if timer.end_time > now:
                self._timers[timer.id] = timer

    def dump(self) -> List[Dict]:
        return [timer.to_dict() for timer in self.list_active()]

    def stop(self) -> None:
        self._running = False
