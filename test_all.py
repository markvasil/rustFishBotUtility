"""Тесты логики всех модулей."""

from __future__ import annotations

import tempfile
from pathlib import Path

from features.craft_calculator.calculator import calculate_craft_summary, create_entry
from features.electricity.calculator import calculate_electricity
from features.furnace_calculator.calculator import calculate_furnace, FurnaceInput, furnace_from_refined
from features.genetics.calculator import calculate_crossbreed, normalize_genes
from features.raid_calculator.calculator import calculate_entry
from features.resource_machines.calculator import calculate_machine
from storage.session import SessionStore


def test_raid():
    e = calculate_entry("stone_wall", 1)
    assert e and e.explosive_count == 2


def test_craft():
    s = calculate_craft_summary([create_entry("c4", 1)])
    assert s.furnace.total_wood == 6500


def test_furnace_multi():
    r1 = calculate_furnace(FurnaceInput(metal_ore=1000), 1)
    r3 = calculate_furnace(FurnaceInput(metal_ore=1000), 3)
    assert r1.total_wood == r3.total_wood
    assert r3.smelt_seconds < r1.smelt_seconds


def test_machine():
    r = calculate_machine("excavator_sulfur", 5)
    assert r and r.outputs["Серная руда"] == 10000


def test_genetics():
    result, slots = calculate_crossbreed("XYYYYY", "GGGGGG", "GGGGGG", "GGGGGG", "GGGGGG")
    assert len(result) == 6
    assert len(slots) == 6
    assert normalize_genes("gy") == "GYXXXX"


def test_electricity():
    s = calculate_electricity({"solar": 2}, {"turret": 3}, {"large": 1})
    assert s.total_generation == 40
    assert s.total_consumption == 30
    assert s.net == 10


def test_session():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "session.json"
        store = SessionStore(path)
        store.set_feature("notes", {"entries": [{"title": "Base", "code": "1234", "note": ""}]})
        store2 = SessionStore(path)
        assert store2.get_feature("notes")["entries"][0]["code"] == "1234"


def test_furnace_from_refined():
    f = furnace_from_refined(sulfur=100, metal_fragments=50, charcoal=200, hqm=4)
    assert f.sulfur_ore == 100
    assert f.metal_ore == 50


if __name__ == "__main__":
    test_raid()
    test_craft()
    test_furnace_multi()
    test_machine()
    test_genetics()
    test_electricity()
    test_session()
    test_furnace_from_refined()
    print("ALL TESTS PASSED")
