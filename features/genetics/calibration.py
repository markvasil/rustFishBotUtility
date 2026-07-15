from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

Offset = Tuple[int, int]


@dataclass
class RegionCalibration:
    dx: int = 0
    dy: int = 0
    slots: Tuple[Offset, Offset, Offset, Offset, Offset, Offset] = field(
        default_factory=lambda: ((0, 0), (0, 0), (0, 0), (0, 0), (0, 0), (0, 0))
    )


def profile_key(profile_id: str | None, ui_resolution: str) -> str:
    mapping = {"Авто": None, "1080p": "1080p", "2K": "1440p"}
    resolved = mapping.get(ui_resolution, ui_resolution)
    return resolved or profile_id or "1080p"


def _empty_slots() -> Tuple[Offset, Offset, Offset, Offset, Offset, Offset]:
    return ((0, 0), (0, 0), (0, 0), (0, 0), (0, 0), (0, 0))


def _parse_region_entry(entry: object) -> RegionCalibration:
    if not isinstance(entry, dict):
        return RegionCalibration()

    slots_raw = entry.get("slots")
    slots = _empty_slots()
    if isinstance(slots_raw, list) and len(slots_raw) == 6:
        parsed: List[Offset] = []
        for item in slots_raw:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                parsed.append((int(item[0]), int(item[1])))
            else:
                parsed.append((0, 0))
        slots = tuple(parsed)  # type: ignore[assignment]

    return RegionCalibration(
        dx=int(entry.get("dx", 0)),
        dy=int(entry.get("dy", 0)),
        slots=slots,
    )


def load_calibrations(
    calibration: dict,
    profile: str,
    region_ids: Sequence[str],
) -> Dict[str, RegionCalibration]:
    profile_data = calibration.get(profile, {})
    if not isinstance(profile_data, dict):
        profile_data = {}

    result: Dict[str, RegionCalibration] = {}
    for region_id in region_ids:
        result[region_id] = _parse_region_entry(profile_data.get(region_id))
    return result


def save_calibrations(
    calibration: dict,
    profile: str,
    calibrations: Dict[str, RegionCalibration],
) -> dict:
    profile_data = calibration.setdefault(profile, {})
    if not isinstance(profile_data, dict):
        profile_data = {}
        calibration[profile] = profile_data

    for region_id, cal in calibrations.items():
        profile_data[region_id] = {
            "dx": int(cal.dx),
            "dy": int(cal.dy),
            "slots": [[int(x), int(y)] for x, y in cal.slots],
        }

    return calibration
