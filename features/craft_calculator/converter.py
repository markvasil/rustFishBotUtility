from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from features.furnace_calculator.calculator import furnace_from_refined
from features.furnace_calculator.data import CHARCOAL_YIELD_PER_WOOD, CRUDE_OIL_PER_LGF

SULFUR_ORE_PER_SULFUR = 1
METAL_ORE_PER_FRAGMENTS = 1


def charcoal_to_wood(charcoal: int) -> int:
    """Сколько дерева нужно сжечь, чтобы получить требуемое кол-во угля."""
    if charcoal <= 0:
        return 0
    return ceil(charcoal / CHARCOAL_YIELD_PER_WOOD)


@dataclass(frozen=True)
class SmeltableRefined:
    """Переработанные ресурсы (после плавки / нефтепереработки)."""

    sulfur: int = 0
    metal_fragments: int = 0
    charcoal: int = 0
    low_grade_fuel: int = 0

    def __add__(self, other: SmeltableRefined) -> SmeltableRefined:
        return SmeltableRefined(
            sulfur=self.sulfur + other.sulfur,
            metal_fragments=self.metal_fragments + other.metal_fragments,
            charcoal=self.charcoal + other.charcoal,
            low_grade_fuel=self.low_grade_fuel + other.low_grade_fuel,
        )


@dataclass(frozen=True)
class SmeltableRaw:
    """Сырьё до переработки (с учётом плавки в печи)."""

    sulfur_ore: int = 0
    metal_ore: int = 0
    wood: int = 0
    crude_oil: int = 0
    hqm_ore: int = 0

    def __add__(self, other: SmeltableRaw) -> SmeltableRaw:
        return SmeltableRaw(
            sulfur_ore=self.sulfur_ore + other.sulfur_ore,
            metal_ore=self.metal_ore + other.metal_ore,
            wood=self.wood + other.wood,
            crude_oil=self.crude_oil + other.crude_oil,
            hqm_ore=self.hqm_ore + other.hqm_ore,
        )


REFINED_LABELS = {
    "sulfur": "Сера",
    "metal_fragments": "Фрагменты металла",
    "charcoal": "Уголь",
    "low_grade_fuel": "Низкокачественное топливо",
}

RAW_LABELS = {
    "sulfur_ore": "Серная руда",
    "metal_ore": "Металлическая руда",
    "wood": "Дерево",
    "crude_oil": "Сырая нефть",
    "hqm_ore": "Руда высокого качества",
}

OTHER_LABELS = {
    "hqm": "Металл высокого качества",
    "scrap": "Металлолом",
    "cloth": "Ткань",
    "tech_trash": "Старые микросхемы",
    "rope": "Верёвка",
    "animal_fat": "Животный жир",
    "metal_pipes": "Металлические трубы",
}


def refined_to_raw(refined: SmeltableRefined, hqm: int = 0) -> SmeltableRaw:
    furnace = furnace_from_refined(
        sulfur=refined.sulfur,
        metal_fragments=refined.metal_fragments,
        charcoal=refined.charcoal,
        hqm=hqm,
    )
    return SmeltableRaw(
        sulfur_ore=furnace.sulfur_ore,
        metal_ore=furnace.metal_ore,
        hqm_ore=furnace.hqm_ore,
        wood=furnace.total_wood,
        crude_oil=refined.low_grade_fuel * CRUDE_OIL_PER_LGF,
    )


def refined_items(refined: SmeltableRefined) -> dict[str, int]:
    return {
        REFINED_LABELS[key]: value
        for key, value in {
            "sulfur": refined.sulfur,
            "metal_fragments": refined.metal_fragments,
            "charcoal": refined.charcoal,
            "low_grade_fuel": refined.low_grade_fuel,
        }.items()
        if value > 0
    }


def raw_items(raw: SmeltableRaw) -> dict[str, int]:
    return {
        RAW_LABELS[key]: value
        for key, value in {
            "sulfur_ore": raw.sulfur_ore,
            "metal_ore": raw.metal_ore,
            "wood": raw.wood,
            "crude_oil": raw.crude_oil,
            "hqm_ore": raw.hqm_ore,
        }.items()
        if value > 0
    }
