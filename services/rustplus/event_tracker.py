from __future__ import annotations

from typing import Any, Dict, List, Set

from rustplus.structs.rust_marker import RustMarker

ALERT_MARKER_TYPES = {
    RustMarker.ChinookMarker,
    RustMarker.CargoShipMarker,
    RustMarker.PatrolHelicopterMarker,
    RustMarker.TravelingVendor,
}


class LiveEventTracker:
    """Отслеживает появление новых событий на карте (карго, верт, chinook)."""

    def __init__(self) -> None:
        self._seen: Set[str] = set()
        self._primed = False

    def reset(self) -> None:
        self._seen.clear()
        self._primed = False

    @staticmethod
    def _event_key(event: Dict[str, Any]) -> str:
        marker_id = event.get("id")
        if marker_id is not None:
            return f"{event.get('type')}:{marker_id}"
        return f"{event.get('type')}:{event.get('grid', '?')}"

    def detect_new(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        alert_events = [e for e in events if e.get("type") in ALERT_MARKER_TYPES]
        keys = {self._event_key(e) for e in alert_events}

        if not self._primed:
            self._seen = keys
            self._primed = True
            return []

        new_keys = keys - self._seen
        self._seen = keys
        return [e for e in alert_events if self._event_key(e) in new_keys]


class TeamTracker:
    """Отслеживает смерти игроков в команде."""

    def __init__(self) -> None:
        self._alive: Dict[int, bool] = {}
        self._primed = False

    def reset(self) -> None:
        self._alive.clear()
        self._primed = False

    def detect_deaths(self, members: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not self._primed:
            for member in members:
                self._alive[int(member.get("steam_id", 0))] = bool(member.get("is_alive", True))
            self._primed = True
            return []

        deaths: List[Dict[str, Any]] = []
        for member in members:
            steam_id = int(member.get("steam_id", 0))
            was_alive = self._alive.get(steam_id, True)
            is_alive = bool(member.get("is_alive", True))
            if was_alive and not is_alive:
                deaths.append(member)
            self._alive[steam_id] = is_alive
        return deaths
