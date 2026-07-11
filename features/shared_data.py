from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

# Время работы на 1 дизель (секунды)
DIESEL_SECONDS_EXCAVATOR = 116  # ~1 мин 56 сек
DIESEL_SECONDS_QUARRY = 130  # ~2 мин 10 сек

MACHINES: Dict[str, dict] = {
    "excavator_stone": {
        "name": "Экскаватор — камень",
        "diesel_seconds": DIESEL_SECONDS_EXCAVATOR,
        "outputs": {"Камень": 10000},
    },
    "excavator_metal": {
        "name": "Экскаватор — металл",
        "diesel_seconds": DIESEL_SECONDS_EXCAVATOR,
        "outputs": {"Фрагменты металла": 5000},
    },
    "excavator_sulfur": {
        "name": "Экскаватор — сера",
        "diesel_seconds": DIESEL_SECONDS_EXCAVATOR,
        "outputs": {"Серная руда": 2000},
    },
    "excavator_hqm": {
        "name": "Экскаватор — HQM",
        "diesel_seconds": DIESEL_SECONDS_EXCAVATOR,
        "outputs": {"Руда высокого качества": 100},
    },
    "quarry_stone": {
        "name": "Карьер — камень",
        "diesel_seconds": DIESEL_SECONDS_QUARRY,
        "outputs": {"Камень": 5000, "Металлическая руда": 1000},
    },
    "quarry_sulfur": {
        "name": "Карьер — сера",
        "diesel_seconds": DIESEL_SECONDS_QUARRY,
        "outputs": {"Серная руда": 1000},
    },
    "quarry_hqm": {
        "name": "Карьер — HQM",
        "diesel_seconds": DIESEL_SECONDS_QUARRY,
        "outputs": {"Руда высокого качества": 50},
    },
    "pump_jack": {
        "name": "Качалка",
        "diesel_seconds": DIESEL_SECONDS_QUARRY,
        "outputs": {"Сырая нефть": 60, "Низкокачественное топливо": 170},
    },
}

DECAY_HOURS: Dict[str, Tuple[str, float]] = {
    "twig": ("Прутья", 1),
    "wood": ("Дерево", 3),
    "stone": ("Камень", 5),
    "metal": ("Листовой металл", 8),
    "armored": ("Бронированный", 12),
}

GENE_WEIGHTS = {"G": 0.6, "Y": 0.6, "H": 0.6, "W": 1.0, "X": 1.0}
VALID_GENES = set("GYHWX")

ELECTRICITY_SOURCES = {
    "solar": ("Солнечная панель", 20),
    "wind": ("Ветряк", 100),
    "generator": ("Генератор", 100),
}

ELECTRICITY_CONSUMERS = {
    "turret": ("Автоматическая турель", 10),
    "siren": ("Сирена", 1),
    "heater": ("Обогреватель", 3),
    "furnace": ("Электропечь", 3),
    "lights": ("Неоновая вывеска", 1),
    "sam": ("Зенитная установка", 25),
    "cctv": ("CCTV", 5),
    "door_controller": ("Контроллер двери", 1),
}

BATTERY_CAPACITY = {
    "small": ("Малая батарея", 1500),
    "large": ("Большая батарея", 15000),
}
