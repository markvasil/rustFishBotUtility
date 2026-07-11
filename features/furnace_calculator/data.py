from __future__ import annotations

# Стандартная печь (vanilla Rust)
# https://rust.fandom.com/wiki/Furnace

# В печи каждое дерево даёт ~70–80% шанс на 1 уголь, в среднем 75%
CHARCOAL_YIELD_PER_WOOD = 0.75

WOOD_PER_METAL_ORE = 5.0
WOOD_PER_SULFUR_ORE = 2.5
WOOD_PER_HQM_ORE = 10.0

SMELT_SECONDS_METAL = 5.0
SMELT_SECONDS_SULFUR = 2.5
SMELT_SECONDS_HQM = 15.0

CRUDE_OIL_PER_LGF = 2

ORE_LABELS = {
    "metal_ore": "Металлическая руда",
    "sulfur_ore": "Серная руда",
    "hqm_ore": "Руда высокого качества",
}

OUTPUT_LABELS = {
    "metal_fragments": "Фрагменты металла",
    "sulfur": "Сера",
    "hqm": "Металл высокого качества",
    "charcoal": "Уголь",
}
