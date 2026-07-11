from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from features.raid_calculator.data import (
    CATEGORY_LABELS,
    CraftCost,
    EXPLOSIVE_BY_ID,
    EXPLOSIVES,
    RESOURCE_LABELS,
    STRUCTURE_BY_ID,
    STRUCTURES,
    Explosive,
    Structure,
)


@dataclass
class RaidEntry:
    structure_id: str
    structure_count: int
    explosive_id: str
    explosive_count: int
    raid_seconds: float
    cost: CraftCost

    @property
    def structure(self) -> Structure:
        return STRUCTURE_BY_ID[self.structure_id]

    @property
    def explosive(self) -> Explosive:
        return EXPLOSIVE_BY_ID[self.explosive_id]


@dataclass
class RaidSummary:
    entries: List[RaidEntry] = field(default_factory=list)
    total_cost: CraftCost = field(default_factory=CraftCost)
    total_seconds: float = 0.0

    def resource_totals(self) -> Dict[str, int]:
        totals: Dict[str, int] = {}
        for key, label in RESOURCE_LABELS.items():
            value = getattr(self.total_cost, key)
            if value > 0:
                totals[label] = value
        return totals


def best_explosive_for(structure_id: str, hp: int) -> Optional[Tuple[str, int, CraftCost]]:
    """Возвращает (explosive_id, count, total_cost) с минимальной серой."""
    best: Optional[Tuple[str, int, CraftCost]] = None
    for explosive in EXPLOSIVES:
        count = explosive.count_for(structure_id, hp)
        if count <= 0:
            continue
        total = explosive.craft.scale(count)
        if best is None or total.sulfur < best[2].sulfur:
            best = (explosive.id, count, total)
    return best


def calculate_entry(
    structure_id: str,
    structure_count: int,
    explosive_id: Optional[str] = None,
) -> Optional[RaidEntry]:
    structure = STRUCTURE_BY_ID.get(structure_id)
    if not structure or structure_count <= 0:
        return None

    if explosive_id is None:
        best = best_explosive_for(structure_id, structure.hp)
        if not best:
            return None
        explosive_id, per_unit_count, _ = best
    else:
        explosive = EXPLOSIVE_BY_ID.get(explosive_id)
        if not explosive:
            return None
        per_unit_count = explosive.count_for(structure_id, structure.hp)
        if per_unit_count <= 0:
            return None

    explosive = EXPLOSIVE_BY_ID[explosive_id]
    total_explosives = per_unit_count * structure_count
    cost = explosive.craft.scale(total_explosives)
    raid_seconds = explosive.raid_seconds * total_explosives

    return RaidEntry(
        structure_id=structure_id,
        structure_count=structure_count,
        explosive_id=explosive_id,
        explosive_count=total_explosives,
        raid_seconds=raid_seconds,
        cost=cost,
    )


def calculate_raid(entries: List[RaidEntry]) -> RaidSummary:
    total = CraftCost()
    seconds = 0.0
    for entry in entries:
        total = total + entry.cost
        seconds += entry.raid_seconds
    return RaidSummary(entries=entries, total_cost=total, total_seconds=seconds)


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


def format_cost_short(cost: CraftCost) -> str:
    parts: List[str] = []
    for key, label in RESOURCE_LABELS.items():
        value = getattr(cost, key)
        if value > 0:
            parts.append(f"{value} {label}")
    return ", ".join(parts) if parts else "—"


def structures_by_category() -> Dict[str, List[Structure]]:
    grouped: Dict[str, List[Structure]] = {}
    for structure in STRUCTURES:
        grouped.setdefault(structure.category, []).append(structure)
    return grouped


def available_explosives_for(structure_id: str) -> List[Explosive]:
    structure = STRUCTURE_BY_ID.get(structure_id)
    if not structure:
        return []
    result: List[Explosive] = []
    for explosive in EXPLOSIVES:
        if explosive.count_for(structure_id, structure.hp) > 0:
            result.append(explosive)
    return sorted(result, key=lambda e: e.craft.scale(
        e.count_for(structure_id, structure.hp)
    ).sulfur)
