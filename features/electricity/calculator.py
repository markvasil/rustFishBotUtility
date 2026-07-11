from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from features.shared_data import BATTERY_CAPACITY, ELECTRICITY_CONSUMERS, ELECTRICITY_SOURCES


@dataclass(frozen=True)
class ElectricityItem:
    item_id: str
    count: int
    label: str
    watts: int


@dataclass(frozen=True)
class ElectricitySummary:
    sources: List[ElectricityItem]
    consumers: List[ElectricityItem]
    batteries: List[ElectricityItem]
    total_generation: int
    total_consumption: int
    total_battery: int
    net: int


def calculate_electricity(
    sources: Dict[str, int],
    consumers: Dict[str, int],
    batteries: Dict[str, int],
) -> ElectricitySummary:
    src_items = [
        ElectricityItem(sid, count, ELECTRICITY_SOURCES[sid][0], ELECTRICITY_SOURCES[sid][1])
        for sid, count in sources.items()
        if count > 0 and sid in ELECTRICITY_SOURCES
    ]
    cons_items = [
        ElectricityItem(cid, count, ELECTRICITY_CONSUMERS[cid][0], ELECTRICITY_CONSUMERS[cid][1])
        for cid, count in consumers.items()
        if count > 0 and cid in ELECTRICITY_CONSUMERS
    ]
    bat_items = [
        ElectricityItem(bid, count, BATTERY_CAPACITY[bid][0], BATTERY_CAPACITY[bid][1])
        for bid, count in batteries.items()
        if count > 0 and bid in BATTERY_CAPACITY
    ]

    total_gen = sum(i.count * i.watts for i in src_items)
    total_cons = sum(i.count * i.watts for i in cons_items)
    total_bat = sum(i.count * i.watts for i in bat_items)

    return ElectricitySummary(
        sources=src_items,
        consumers=cons_items,
        batteries=bat_items,
        total_generation=total_gen,
        total_consumption=total_cons,
        total_battery=total_bat,
        net=total_gen - total_cons,
    )
