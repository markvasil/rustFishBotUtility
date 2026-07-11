from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Dict, List

from features.furnace_calculator.data import (
    CHARCOAL_YIELD_PER_WOOD,
    ORE_LABELS,
    OUTPUT_LABELS,
    SMELT_SECONDS_HQM,
    SMELT_SECONDS_METAL,
    SMELT_SECONDS_SULFUR,
    WOOD_PER_HQM_ORE,
    WOOD_PER_METAL_ORE,
    WOOD_PER_SULFUR_ORE,
)


def charcoal_to_wood(charcoal: int) -> int:
    if charcoal <= 0:
        return 0
    return ceil(charcoal / CHARCOAL_YIELD_PER_WOOD)


@dataclass(frozen=True)
class FurnaceInput:
    metal_ore: int = 0
    sulfur_ore: int = 0
    hqm_ore: int = 0
    charcoal_needed: int = 0

    def __add__(self, other: FurnaceInput) -> FurnaceInput:
        return FurnaceInput(
            metal_ore=self.metal_ore + other.metal_ore,
            sulfur_ore=self.sulfur_ore + other.sulfur_ore,
            hqm_ore=self.hqm_ore + other.hqm_ore,
            charcoal_needed=self.charcoal_needed + other.charcoal_needed,
        )


@dataclass(frozen=True)
class FurnaceResult:
    metal_ore: int = 0
    sulfur_ore: int = 0
    hqm_ore: int = 0
    wood_smelting: int = 0
    wood_extra_charcoal: int = 0
    total_wood: int = 0
    charcoal_from_smelting: int = 0
    charcoal_deficit: int = 0
    output_metal: int = 0
    output_sulfur: int = 0
    output_hqm: int = 0
    smelt_seconds: float = 0.0
    smelt_seconds_single: float = 0.0
    furnace_count: int = 1

    def ore_totals(self) -> Dict[str, int]:
        items = {
            "metal_ore": self.metal_ore,
            "sulfur_ore": self.sulfur_ore,
            "hqm_ore": self.hqm_ore,
        }
        return {ORE_LABELS[k]: v for k, v in items.items() if v > 0}

    def output_totals(self) -> Dict[str, int]:
        items = {
            "metal_fragments": self.output_metal,
            "sulfur": self.output_sulfur,
            "hqm": self.output_hqm,
            "charcoal": self.charcoal_from_smelting,
        }
        return {OUTPUT_LABELS[k]: v for k, v in items.items() if v > 0}

    def smelting_breakdown(self) -> Dict[str, int]:
        result: Dict[str, int] = {}
        if self.wood_smelting > 0:
            result["Дерево на плавку руды"] = self.wood_smelting
        if self.charcoal_from_smelting > 0:
            result["Уголь с плавки (~75%)"] = self.charcoal_from_smelting
        if self.wood_extra_charcoal > 0:
            result["Доп. дерево на уголь"] = self.wood_extra_charcoal
        if self.total_wood > 0:
            result["Итого дерево"] = self.total_wood
        return result


def calculate_furnace(inp: FurnaceInput, furnace_count: int = 1) -> FurnaceResult:
    metal_ore = max(0, inp.metal_ore)
    sulfur_ore = max(0, inp.sulfur_ore)
    hqm_ore = max(0, inp.hqm_ore)
    charcoal_needed = max(0, inp.charcoal_needed)
    furnaces = max(1, furnace_count)

    wood_metal = ceil(metal_ore * WOOD_PER_METAL_ORE) if metal_ore else 0
    wood_sulfur = ceil(sulfur_ore * WOOD_PER_SULFUR_ORE) if sulfur_ore else 0
    wood_hqm = ceil(hqm_ore * WOOD_PER_HQM_ORE) if hqm_ore else 0
    wood_smelting = wood_metal + wood_sulfur + wood_hqm

    charcoal_from_smelting = int(wood_smelting * CHARCOAL_YIELD_PER_WOOD)
    charcoal_deficit = max(0, charcoal_needed - charcoal_from_smelting)
    wood_extra = charcoal_to_wood(charcoal_deficit)
    total_wood = wood_smelting + wood_extra

    smelt_seconds_single = (
        metal_ore * SMELT_SECONDS_METAL
        + sulfur_ore * SMELT_SECONDS_SULFUR
        + hqm_ore * SMELT_SECONDS_HQM
    )
    smelt_seconds = smelt_seconds_single / furnaces

    return FurnaceResult(
        metal_ore=metal_ore,
        sulfur_ore=sulfur_ore,
        hqm_ore=hqm_ore,
        wood_smelting=wood_smelting,
        wood_extra_charcoal=wood_extra,
        total_wood=total_wood,
        charcoal_from_smelting=charcoal_from_smelting,
        charcoal_deficit=charcoal_deficit,
        output_metal=metal_ore,
        output_sulfur=sulfur_ore,
        output_hqm=hqm_ore,
        smelt_seconds=smelt_seconds,
        smelt_seconds_single=smelt_seconds_single,
        furnace_count=furnaces,
    )


def furnace_from_refined(
    sulfur: int = 0,
    metal_fragments: int = 0,
    charcoal: int = 0,
    hqm: int = 0,
) -> FurnaceResult:
    """План плавки для получения переработанных ресурсов под крафт."""
    return calculate_furnace(
        FurnaceInput(
            sulfur_ore=sulfur,
            metal_ore=metal_fragments,
            hqm_ore=hqm,
            charcoal_needed=charcoal,
        )
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
