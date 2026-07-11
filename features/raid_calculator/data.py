from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class CraftCost:
    sulfur: int = 0
    metal_fragments: int = 0
    charcoal: int = 0
    hqm: int = 0
    scrap: int = 0
    cloth: int = 0
    tech_trash: int = 0
    rope: int = 0
    animal_fat: int = 0
    low_grade_fuel: int = 0
    metal_pipes: int = 0

    def __add__(self, other: CraftCost) -> CraftCost:
        return CraftCost(
            sulfur=self.sulfur + other.sulfur,
            metal_fragments=self.metal_fragments + other.metal_fragments,
            charcoal=self.charcoal + other.charcoal,
            hqm=self.hqm + other.hqm,
            scrap=self.scrap + other.scrap,
            cloth=self.cloth + other.cloth,
            tech_trash=self.tech_trash + other.tech_trash,
            rope=self.rope + other.rope,
            animal_fat=self.animal_fat + other.animal_fat,
            low_grade_fuel=self.low_grade_fuel + other.low_grade_fuel,
            metal_pipes=self.metal_pipes + other.metal_pipes,
        )

    def scale(self, count: int) -> CraftCost:
        return CraftCost(
            sulfur=self.sulfur * count,
            metal_fragments=self.metal_fragments * count,
            charcoal=self.charcoal * count,
            hqm=self.hqm * count,
            scrap=self.scrap * count,
            cloth=self.cloth * count,
            tech_trash=self.tech_trash * count,
            rope=self.rope * count,
            animal_fat=self.animal_fat * count,
            low_grade_fuel=self.low_grade_fuel * count,
            metal_pipes=self.metal_pipes * count,
        )


@dataclass(frozen=True)
class Explosive:
    id: str
    name: str
    craft: CraftCost
    # Урон по id структуры (из игровых данных, soft-side)
    damage: Dict[str, float]
    raid_seconds: float = 0.0

    def count_for(self, structure_id: str, hp: int) -> int:
        dmg = self.damage.get(structure_id, 0)
        if dmg <= 0:
            return 0
        return ceil(hp / dmg)


@dataclass(frozen=True)
class Structure:
    id: str
    name: str
    hp: int
    category: str


STRUCTURES: List[Structure] = [
    Structure("wooden_wall", "Деревянная стена", 250, "walls"),
    Structure("stone_wall", "Стена из камня", 500, "walls"),
    Structure("metal_wall", "Металлическая стена", 1000, "walls"),
    Structure("armored_wall", "Бронированная стена", 2000, "walls"),
    Structure("wooden_door", "Деревянная дверь", 200, "doors"),
    Structure("sheet_metal_door", "Дверь из листового металла", 250, "doors"),
    Structure("garage_door", "Гаражная дверь", 600, "doors"),
    Structure("armored_door", "Бронированная дверь", 800, "doors"),
    Structure("ladder_hatch", "Люк с лестницей", 250, "doors"),
    Structure("metal_shop_front", "Металлическая витрина", 750, "doors"),
    Structure("external_wooden_wall", "Высокая деревянная стена", 500, "external"),
    Structure("external_stone_wall", "Высокая каменная стена", 500, "external"),
    Structure("tool_cupboard", "Шкаф с инструментами", 600, "deployables"),
    Structure("auto_turret", "Автоматическая турель", 1000, "traps"),
    Structure("shotgun_trap", "Дробовая ловушка", 300, "traps"),
    Structure("flame_turret", "Огнемётная турель", 300, "traps"),
    Structure("sam_site", "Зенитная установка", 1000, "traps"),
    Structure("metal_barricade", "Металлическая баррикада", 500, "deployables"),
    Structure("chainlink_fence", "Сетчатый забор", 100, "deployables"),
    Structure("floor_grill", "Напольная решётка", 250, "deployables"),
    Structure("glass_window", "Стеклянное окно", 125, "deployables"),
    Structure("reinforced_window", "Укреплённое окно", 500, "deployables"),
    Structure("metal_embrasure", "Металлическая бойница", 500, "deployables"),
    Structure("vending_machine", "Торговый автомат", 500, "deployables"),
    Structure("workbench_1", "Верстак 1 уровня", 500, "deployables"),
    Structure("workbench_2", "Верстак 2 уровня", 500, "deployables"),
    Structure("workbench_3", "Верстак 3 уровня", 750, "deployables"),
]

STRUCTURE_BY_ID = {s.id: s for s in STRUCTURES}

CATEGORY_LABELS = {
    "walls": "Стены",
    "doors": "Двери",
    "external": "Внешние стены",
    "traps": "Ловушки и турели",
    "deployables": "Объекты",
}

EXPLOSIVES: List[Explosive] = [
    Explosive(
        "c4",
        "Взрывчатка с таймером",
        CraftCost(
            sulfur=2200,
            metal_fragments=200,
            charcoal=3000,
            cloth=5,
            tech_trash=2,
            animal_fat=45,
        ),
        damage={
            "wooden_wall": 550,
            "stone_wall": 275,
            "metal_wall": 275,
            "armored_wall": 275,
            "wooden_door": 550,
            "sheet_metal_door": 440,
            "garage_door": 440,
            "armored_door": 440,
            "ladder_hatch": 440,
            "metal_shop_front": 275,
            "external_wooden_wall": 550,
            "external_stone_wall": 275,
            "tool_cupboard": 440,
            "auto_turret": 275,
            "shotgun_trap": 550,
            "flame_turret": 550,
            "sam_site": 275,
            "metal_barricade": 275,
            "chainlink_fence": 550,
            "floor_grill": 440,
            "glass_window": 550,
            "reinforced_window": 275,
            "metal_embrasure": 275,
            "vending_machine": 275,
            "workbench_1": 550,
            "workbench_2": 275,
            "workbench_3": 275,
        },
        raid_seconds=10,
    ),
    Explosive(
        "rocket",
        "Ракета",
        CraftCost(
            sulfur=1400,
            metal_fragments=100,
            charcoal=1950,
            hqm=4,
            scrap=40,
            cloth=7,
            animal_fat=22,
            metal_pipes=2,
        ),
        damage={
            "wooden_wall": 247.65,
            "stone_wall": 137.65,
            "metal_wall": 137.65,
            "armored_wall": 137.575,
            "wooden_door": 247.65,
            "sheet_metal_door": 247.65,
            "garage_door": 247.65,
            "armored_door": 247.65,
            "ladder_hatch": 247.65,
            "metal_shop_front": 137.65,
            "external_wooden_wall": 247.65,
            "external_stone_wall": 137.65,
            "tool_cupboard": 247.65,
            "auto_turret": 137.65,
            "shotgun_trap": 247.65,
            "flame_turret": 247.65,
            "sam_site": 137.65,
            "metal_barricade": 137.65,
            "chainlink_fence": 247.65,
            "floor_grill": 247.65,
            "glass_window": 247.65,
            "reinforced_window": 137.65,
            "metal_embrasure": 137.65,
            "vending_machine": 137.65,
            "workbench_1": 247.65,
            "workbench_2": 137.65,
            "workbench_3": 137.65,
        },
        raid_seconds=15,
    ),
    Explosive(
        "satchel",
        "Связка бобовых гранат",
        CraftCost(
            sulfur=480,
            metal_fragments=80,
            charcoal=720,
            cloth=10,
            rope=1,
        ),
        damage={
            "wooden_wall": 91.5,
            "stone_wall": 51.5,
            "metal_wall": 43.5,
            "armored_wall": 43.5,
            "wooden_door": 91.5,
            "sheet_metal_door": 70,
            "garage_door": 70,
            "armored_door": 70,
            "ladder_hatch": 70,
            "metal_shop_front": 51.5,
            "external_wooden_wall": 91.5,
            "external_stone_wall": 51.5,
            "tool_cupboard": 70,
            "auto_turret": 43.5,
            "shotgun_trap": 91.5,
            "flame_turret": 91.5,
            "sam_site": 43.5,
            "metal_barricade": 51.5,
            "chainlink_fence": 91.5,
            "floor_grill": 70,
            "glass_window": 91.5,
            "reinforced_window": 51.5,
            "metal_embrasure": 51.5,
            "vending_machine": 51.5,
            "workbench_1": 91.5,
            "workbench_2": 51.5,
            "workbench_3": 51.5,
        },
        raid_seconds=8,
    ),
    Explosive(
        "explosive_ammo",
        "Патрон 5.56 (разрывной)",
        CraftCost(sulfur=25, metal_fragments=5, charcoal=30),
        damage={
            "wooden_wall": 2.704,
            "stone_wall": 2.704,
            "metal_wall": 2.5,
            "armored_wall": 2.5,
            "wooden_door": 10.566,
            "sheet_metal_door": 4.0064,
            "garage_door": 4.0064,
            "armored_door": 3.1536,
            "ladder_hatch": 4.0064,
            "metal_shop_front": 2.704,
            "external_wooden_wall": 2.704,
            "external_stone_wall": 2.704,
            "tool_cupboard": 4.0064,
            "auto_turret": 2.5,
            "shotgun_trap": 4.0064,
            "flame_turret": 4.0064,
            "sam_site": 2.5,
            "metal_barricade": 2.704,
            "chainlink_fence": 4.0064,
            "floor_grill": 4.0064,
            "glass_window": 4.0064,
            "reinforced_window": 2.704,
            "metal_embrasure": 2.704,
            "vending_machine": 2.704,
            "workbench_1": 4.0064,
            "workbench_2": 2.704,
            "workbench_3": 2.704,
        },
        raid_seconds=0.25,
    ),
    Explosive(
        "beancan",
        "Бобовая граната",
        CraftCost(sulfur=120, metal_fragments=20, charcoal=180),
        damage={
            "wooden_wall": 19.5,
            "stone_wall": 11,
            "metal_wall": 9.5,
            "armored_wall": 9.5,
            "wooden_door": 19.5,
            "sheet_metal_door": 14.5,
            "garage_door": 14.5,
            "armored_door": 14.5,
            "ladder_hatch": 14.5,
            "metal_shop_front": 11,
            "external_wooden_wall": 19.5,
            "external_stone_wall": 11,
            "tool_cupboard": 14.5,
            "auto_turret": 9.5,
            "shotgun_trap": 19.5,
            "flame_turret": 19.5,
            "sam_site": 9.5,
            "metal_barricade": 11,
            "chainlink_fence": 19.5,
            "floor_grill": 14.5,
            "glass_window": 19.5,
            "reinforced_window": 11,
            "metal_embrasure": 11,
            "vending_machine": 11,
            "workbench_1": 19.5,
            "workbench_2": 11,
            "workbench_3": 11,
        },
        raid_seconds=6,
    ),
    Explosive(
        "hv_rocket",
        "Ракета высокоскоростная",
        CraftCost(sulfur=100, metal_fragments=75, charcoal=150),
        damage={
            "wooden_wall": 91.25,
            "stone_wall": 0,
            "metal_wall": 0,
            "armored_wall": 0,
            "wooden_door": 91.25,
            "sheet_metal_door": 0,
            "garage_door": 0,
            "armored_door": 0,
            "ladder_hatch": 0,
            "metal_shop_front": 0,
            "external_wooden_wall": 91.25,
            "external_stone_wall": 0,
            "tool_cupboard": 0,
            "auto_turret": 91.25,
            "shotgun_trap": 91.25,
            "flame_turret": 91.25,
            "sam_site": 91.25,
            "metal_barricade": 0,
            "chainlink_fence": 91.25,
            "floor_grill": 0,
            "glass_window": 0,
            "reinforced_window": 0,
            "metal_embrasure": 0,
            "vending_machine": 0,
            "workbench_1": 91.25,
            "workbench_2": 0,
            "workbench_3": 0,
        },
        raid_seconds=12,
    ),
]

EXPLOSIVE_BY_ID = {e.id: e for e in EXPLOSIVES}

RESOURCE_LABELS = {
    "sulfur": "Сера",
    "metal_fragments": "Фрагменты металла",
    "charcoal": "Уголь",
    "hqm": "Металл высокого качества",
    "scrap": "Металлолом",
    "cloth": "Ткань",
    "tech_trash": "Старые микросхемы",
    "rope": "Верёвка",
    "animal_fat": "Животный жир",
    "low_grade_fuel": "Низкокачественное топливо",
    "metal_pipes": "Металлические трубы",
}
