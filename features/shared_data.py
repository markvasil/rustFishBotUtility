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
    # Facepunch Wiki / RustHelp: max output
    "solar": ("Солнечная панель", 20),
    "wind": ("Ветряк", 150),
    "generator": ("Генератор", 40),
}

ELECTRICITY_CONSUMERS = {
    # Значения IO Consumption: Facepunch Wiki + RustHelp (дампы игры)
    "turret": ("Автоматическая турель", 10),
    "sam": ("Зенитная установка", 25),
    "heater": ("Электрообогреватель", 3),
    "furnace": ("Электропечь", 3),
    "ceiling_light": ("Потолочный свет", 2),
    "simple_light": ("Простой свет", 1),
    "flasher": ("Мигающий свет", 1),
    "siren_light": ("Сигнальный свет", 1),
    "search_light": ("Прожектор", 10),
    "neon_sign_large": ("Неоновая вывеска (большая)", 6),
    "neon_sign_medium": ("Неоновая вывеска (средняя)", 4),
    "neon_sign_small": ("Неоновая вывеска (малая)", 2),
    "string_lights": ("Гирлянда", 1),
    "audio_alarm": ("Звуковая сигнализация", 1),
    "smart_alarm": ("Умная сигнализация", 1),
    "cctv": ("CCTV камера", 3),
    "ptz_cctv": ("PTZ камера", 3),
    "door_controller": ("Контроллер двери", 1),
    "igniter": ("Воспламенитель", 2),
    "storage_monitor": ("Монитор хранилища", 1),
    "elevator": ("Лифт", 5),
    "car_lift": ("Автоподъёмник", 5),
    "tesla": ("Катушка Теслы", 25),
    "water_pump": ("Водяной насос", 5),
    "water_purifier": ("Очиститель воды", 5),
    "fluid_switch": ("Жидкостный насос", 1),
    "hbhf": ("HBHF датчик", 1),
    "laser_detector": ("Лазерный датчик", 1),
    "reactive_target": ("Мишень", 1),
    "button": ("Кнопка", 1),
    "pressure_pad": ("Нажимная плита", 1),
    "sprinkler": ("Разбрызгиватель", 1),
    "vending_machine": ("Торговый автомат", 5),
    "boombox": ("Бумбокс", 10),
    "mini_fridge": ("Холодильник", 5),
    "telephone": ("Телефон", 1),
    "rf_broadcaster": ("RF передатчик", 1),
    "rf_receiver": ("RF приёмник", 1),
    "sound_light": ("Светомузыка", 1),
}

BATTERY_CAPACITY = {
    # Facepunch Wiki: Power Capacity (rWm)
    "medium": ("Средний аккумулятор", 9000),
    "large": ("Большой аккумулятор", 24000),
}
