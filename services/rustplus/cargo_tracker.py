from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from rustplus.structs.rust_marker import RustMarker


class CargoTracker:
    """Карго-интеллект: маршрут, стоянка в порту, предупреждение в чат."""

    HARBOR_GRIDS = {"E4", "E5", "F4", "F5", "G4"}
    DEFAULT_HARBOR_SECONDS = 600

    def __init__(
        self,
        *,
        harbor_seconds: int = DEFAULT_HARBOR_SECONDS,
        send_chat: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._harbor_seconds = harbor_seconds
        self._send_chat = send_chat
        self._route: List[str] = []
        self._last_grid: Optional[str] = None
        self._harbor_since: Optional[float] = None
        self._last_seen_at: Optional[float] = None
        self._warned_departure = False
        self._announced_arrival_grid: Optional[str] = None
        self._announced_docking_grid: Optional[str] = None
        self._cargo_seen = False

    def reset(self) -> None:
        self._route.clear()
        self._last_grid = None
        self._harbor_since = None
        self._last_seen_at = None
        self._warned_departure = False
        self._announced_arrival_grid = None
        self._announced_docking_grid = None
        self._cargo_seen = False

    def hydrate(self, state: Dict[str, Any]) -> None:
        self._route = [str(x) for x in state.get("route", []) if x]
        self._last_grid = str(state.get("last_grid")) if state.get("last_grid") else None
        self._harbor_seconds = int(state.get("harbor_seconds", self.DEFAULT_HARBOR_SECONDS))

    def export_state(self) -> Dict[str, Any]:
        return {
            "route": list(self._route[-12:]),
            "last_grid": self._last_grid,
            "harbor_seconds": int(self._harbor_seconds),
        }

    def update(self, events: List[Dict[str, Any]], grid_hint: str = "") -> Dict[str, Any]:
        cargo = next((e for e in events if e.get("type") == RustMarker.CargoShipMarker), None)
        if not cargo:
            self._harbor_since = None
            self._warned_departure = False
            self._announced_docking_grid = None
            return {"alerts": [], "status": None}

        grid = cargo.get("grid") or grid_hint or "?"
        now = time.time()
        self._cargo_seen = True
        self._last_seen_at = now
        alerts: List[Dict[str, str]] = []

        if grid != self._last_grid:
            if self._last_grid and grid not in self._route[-6:]:
                self._route.append(grid)
            self._last_grid = grid
            if grid != self._announced_arrival_grid:
                alerts.append(
                    {
                        "kind": "cargo_arrival",
                        "message": f"🚢 Карго замечен [{grid}]",
                    }
                )
                self._announced_arrival_grid = grid
            if grid in self.HARBOR_GRIDS:
                self._harbor_since = now
                self._warned_departure = False
                if grid != self._announced_docking_grid:
                    alerts.append(
                        {
                            "kind": "cargo_docking",
                            "message": f"⚓ Карго встал в порт [{grid}]",
                        }
                    )
                    self._announced_docking_grid = grid
            else:
                self._harbor_since = None

        if self._harbor_since and not self._warned_departure:
            elapsed = now - self._harbor_since
            remaining = self._harbor_seconds - elapsed
            if remaining <= 300 and self._send_chat:
                minutes = max(1, int(remaining / 60))
                msg = f"🚢 Карго в порту — уходит примерно через {minutes} мин [{grid}]"
                self._warned_departure = True
                alerts.append({"kind": "cargo_departure", "message": msg})
        return {
            "alerts": alerts,
            "status": {
                "grid": grid,
                "route": list(self._route[-6:]),
                "in_harbor": self.in_harbor,
                "remaining_minutes": self.harbor_remaining_minutes(),
            },
        }

    @property
    def route(self) -> List[str]:
        return list(self._route)

    @property
    def in_harbor(self) -> bool:
        return self._harbor_since is not None

    def harbor_remaining_minutes(self) -> Optional[int]:
        if not self._harbor_since:
            return None
        remaining = self._harbor_seconds - (time.time() - self._harbor_since)
        return max(0, int(remaining / 60))
