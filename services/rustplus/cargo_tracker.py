from __future__ import annotations

import math
import time
from typing import Any, Callable, Dict, List, Optional

from rustplus.structs.rust_marker import RustMarker


class CargoTracker:
    """Карго-интеллект: маршрут, стоянка в порту, предупреждение в чат."""

    DEFAULT_HARBOR_SECONDS = 600
    # Скорость ниже порога + удержание в одном квадрате = стоянка в порту.
    STATIONARY_SPEED = 0.85
    DOCK_CONFIRM_SEC = 75

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

    @staticmethod
    def _speed(cargo: Dict[str, Any]) -> float:
        try:
            vx = float(cargo.get("_vx") or 0.0)
            vy = float(cargo.get("_vy") or 0.0)
        except (TypeError, ValueError):
            return 0.0
        return math.hypot(vx, vy)

    def update(self, events: List[Dict[str, Any]], grid_hint: str = "") -> Dict[str, Any]:
        cargo = next((e for e in events if e.get("type") == RustMarker.CargoShipMarker), None)
        if not cargo:
            if self._cargo_seen:
                self.reset()
            else:
                self._harbor_since = None
                self._warned_departure = False
                self._announced_docking_grid = None
            return {"alerts": [], "status": None}

        grid = str(cargo.get("grid") or grid_hint or "?")
        now = time.time()
        first_seen = not self._cargo_seen
        self._cargo_seen = True
        self._last_seen_at = now
        alerts: List[Dict[str, str]] = []
        speed = self._speed(cargo)

        if grid != self._last_grid:
            if self._last_grid and grid not in self._route[-6:]:
                self._route.append(grid)
            self._last_grid = grid
            # Смена квадрата — точно не стоянка в порту.
            self._harbor_since = None
            if self._announced_docking_grid and self._announced_docking_grid != grid:
                self._announced_docking_grid = None
                self._warned_departure = False

        # Arrival только при первом появлении (не на каждый квадрат маршрута).
        if first_seen and grid != self._announced_arrival_grid:
            alerts.append(
                {
                    "kind": "cargo_arrival",
                    "message": f"🚢 Карго замечен [{grid}]",
                }
            )
            self._announced_arrival_grid = grid

        # Докинг: почти нулевая скорость в одном квадрате дольше DOCK_CONFIRM_SEC.
        if speed < self.STATIONARY_SPEED and grid and grid != "?":
            if self._harbor_since is None:
                self._harbor_since = now
            elif (
                now - self._harbor_since >= self.DOCK_CONFIRM_SEC
                and grid != self._announced_docking_grid
            ):
                alerts.append(
                    {
                        "kind": "cargo_docking",
                        "message": f"⚓ Карго встал в порт [{grid}]",
                    }
                )
                self._announced_docking_grid = grid
                self._warned_departure = False
        elif speed >= self.STATIONARY_SPEED:
            self._harbor_since = None

        if self._harbor_since and self._announced_docking_grid and not self._warned_departure:
            elapsed = now - self._harbor_since
            remaining = self._harbor_seconds - elapsed
            if remaining <= 300:
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
                "harbor_since": self._harbor_since if self.in_harbor else None,
                "harbor_seconds": int(self._harbor_seconds),
            },
        }

    @property
    def route(self) -> List[str]:
        return list(self._route)

    @property
    def in_harbor(self) -> bool:
        return self._announced_docking_grid is not None and self._harbor_since is not None

    def harbor_remaining_minutes(self) -> Optional[int]:
        if not self._harbor_since or not self._announced_docking_grid:
            return None
        remaining = self._harbor_seconds - (time.time() - self._harbor_since)
        return max(0, int(remaining / 60))
