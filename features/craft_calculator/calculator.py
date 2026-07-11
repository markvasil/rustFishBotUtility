from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from features.craft_calculator.converter import (
    OTHER_LABELS,
    SmeltableRaw,
    SmeltableRefined,
    raw_items,
    refined_items,
    refined_to_raw,
)
from features.furnace_calculator.calculator import FurnaceResult, furnace_from_refined
from features.raid_calculator.data import CraftCost, EXPLOSIVE_BY_ID, Explosive


@dataclass
class CraftEntry:
    explosive_id: str
    count: int

    @property
    def explosive(self) -> Explosive:
        return EXPLOSIVE_BY_ID[self.explosive_id]

    @property
    def cost(self) -> CraftCost:
        return self.explosive.craft.scale(self.count)


@dataclass
class CraftSummary:
    entries: List[CraftEntry] = field(default_factory=list)
    total_cost: CraftCost = field(default_factory=CraftCost)
    refined: SmeltableRefined = field(default_factory=SmeltableRefined)
    raw: SmeltableRaw = field(default_factory=SmeltableRaw)
    other: CraftCost = field(default_factory=CraftCost)
    furnace: FurnaceResult = field(default_factory=FurnaceResult)

    def refined_totals(self) -> Dict[str, int]:
        return refined_items(self.refined)

    def raw_totals(self) -> Dict[str, int]:
        return raw_items(self.raw)

    def other_totals(self) -> Dict[str, int]:
        result: Dict[str, int] = {}
        for key, label in OTHER_LABELS.items():
            value = getattr(self.other, key)
            if value > 0:
                result[label] = value
        return result

    def furnace_breakdown(self) -> Dict[str, int]:
        return self.furnace.smelting_breakdown()


def _split_smeltable(cost: CraftCost) -> tuple[SmeltableRefined, CraftCost]:
    refined = SmeltableRefined(
        sulfur=cost.sulfur,
        metal_fragments=cost.metal_fragments,
        charcoal=cost.charcoal,
        low_grade_fuel=cost.low_grade_fuel,
    )
    other = CraftCost(
        hqm=cost.hqm,
        scrap=cost.scrap,
        cloth=cost.cloth,
        tech_trash=cost.tech_trash,
        rope=cost.rope,
        animal_fat=cost.animal_fat,
        metal_pipes=cost.metal_pipes,
    )
    return refined, other


def calculate_craft_summary(entries: List[CraftEntry]) -> CraftSummary:
    total = CraftCost()
    refined = SmeltableRefined()
    other = CraftCost()

    for entry in entries:
        cost = entry.cost
        total = total + cost
        entry_refined, entry_other = _split_smeltable(cost)
        refined = refined + entry_refined
        other = other + entry_other

    furnace = furnace_from_refined(
        sulfur=refined.sulfur,
        metal_fragments=refined.metal_fragments,
        charcoal=refined.charcoal,
        hqm=other.hqm,
    )
    raw = refined_to_raw(refined, hqm=other.hqm)

    return CraftSummary(
        entries=entries,
        total_cost=total,
        refined=refined,
        raw=raw,
        other=other,
        furnace=furnace,
    )


def create_entry(explosive_id: str, count: int) -> CraftEntry | None:
    if explosive_id not in EXPLOSIVE_BY_ID or count <= 0:
        return None
    return CraftEntry(explosive_id=explosive_id, count=count)
