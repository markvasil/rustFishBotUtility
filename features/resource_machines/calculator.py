from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from features.shared_data import MACHINES


@dataclass(frozen=True)
class MachineResult:
    machine_id: str
    diesel: int
    seconds: float
    outputs: Dict[str, int]

    @property
    def name(self) -> str:
        return MACHINES[self.machine_id]["name"]


def calculate_machine(machine_id: str, diesel: int) -> MachineResult | None:
    if machine_id not in MACHINES or diesel <= 0:
        return None
    cfg = MACHINES[machine_id]
    per_diesel = cfg["diesel_seconds"]
    outputs = {k: v * diesel for k, v in cfg["outputs"].items()}
    return MachineResult(
        machine_id=machine_id,
        diesel=diesel,
        seconds=per_diesel * diesel,
        outputs=outputs,
    )


def format_duration(seconds: float) -> str:
    total = int(seconds)
    if total <= 0:
        return "0 сек"
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    parts: List[str] = []
    if hours:
        parts.append(f"{hours} ч")
    if minutes:
        parts.append(f"{minutes} мин")
    if secs or not parts:
        parts.append(f"{secs} сек")
    return " ".join(parts)
