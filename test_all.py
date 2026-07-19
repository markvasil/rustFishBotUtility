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
from features.shared_data import BATTERY_CAPACITY, ELECTRICITY_CONSUMERS, ELECTRICITY_SOURCES
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


def test_genetics_breeding_planner():
    from features.genetics.breeding_planner import (
        find_breeding_paths,
        format_gene_profile,
        gene_counts,
        matches_gene_counts,
        parse_target_counts,
        validate_path,
    )

    counts, err = parse_target_counts({"G": 3, "Y": 3, "H": 0, "W": 0, "X": 0})
    assert err is None
    assert format_gene_profile(counts) == "3G 3Y"

    direct, err = find_breeding_paths(["YYGYGG"], counts, max_steps=2, max_paths=3)
    assert err is None
    assert direct and direct[0].step_count == 0
    assert matches_gene_counts(direct[0].final, counts)

    pool = ["WYGXGH", "HGGWYX", "YGHWWH"]
    target_counts = gene_counts("YGGWWH")
    paths, err = find_breeding_paths(pool, target_counts, max_steps=3, max_paths=3)
    assert err is None
    assert paths and paths[0].step_count >= 1
    assert matches_gene_counts(paths[0].final, target_counts)
    for path in paths:
        assert validate_path(pool, path.steps)

    user_pool = ["GGYXYH", "HGWGYW", "XHHGGX"]
    user_target = {"G": 3, "Y": 2, "H": 1, "W": 0, "X": 0}
    user_paths, user_err = find_breeding_paths(
        user_pool,
        user_target,
        max_steps=2,
        max_paths=3,
    )
    assert not user_paths
    assert user_err

    missing, err = find_breeding_paths(["GGGGGG", "YYYYYY"], counts, max_steps=2, max_paths=3)
    assert not missing
    assert err


def test_electricity():
    s = calculate_electricity({"solar": 2}, {"turret": 3}, {"large": 1})
    assert s.total_generation == 40
    assert s.total_consumption == 30
    assert s.net == 10
    assert s.total_battery == 24000

    m = calculate_electricity({"wind": 1}, {"sam": 2, "heater": 1}, {"medium": 2})
    assert m.total_generation == 150
    assert m.total_consumption == 53
    assert m.net == 97
    assert m.total_battery == 18000
    assert "small" not in BATTERY_CAPACITY
    assert set(BATTERY_CAPACITY) == {"medium", "large"}
    assert len(ELECTRICITY_CONSUMERS) >= 30
    assert BATTERY_CAPACITY["medium"][0] == "Средний аккумулятор"
    assert BATTERY_CAPACITY["large"][0] == "Большой аккумулятор"
    assert ELECTRICITY_CONSUMERS["water_pump"][1] == 5
    assert ELECTRICITY_CONSUMERS["tesla"][1] == 25
    assert ELECTRICITY_CONSUMERS["cctv"][1] == 3
    assert ELECTRICITY_SOURCES["generator"][1] == 40


def test_session():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "session.json"
        store = SessionStore(path)
        store.set_feature("notes", {"text": "база A\nкод 1234"})
        store2 = SessionStore(path)
        assert store2.get_feature("notes")["text"] == "база A\nкод 1234"


def test_furnace_from_refined():
    f = furnace_from_refined(sulfur=100, metal_fragments=50, charcoal=200, hqm=4)
    assert f.sulfur_ore == 100
    assert f.metal_ore == 50


def test_cargo_live_grid_and_tracker():
    from rustplus.structs.rust_marker import RustMarker
    from services.rustplus.cargo_tracker import CargoTracker
    from services.rustplus.live_format import add_motion_vectors, world_to_grid
    from services.rustplus.grid_coords import GRID_DIAMETER, GRID_ORIGIN

    assert world_to_grid(0, 4000, 4000) == "A0"
    # Граница Q/R со сдвигом origin: ORIGIN + 17*150 = 2625.
    q_r = GRID_ORIGIN + 17 * GRID_DIAMETER
    assert abs(q_r - 2625.0) < 1e-6
    assert world_to_grid(q_r - 1, 250, 3800).startswith("Q")
    assert world_to_grid(q_r + 1, 250, 3800).startswith("R")
    # Без сдвига (2550) точка уезжала в «середину» R — со сдвигом это ещё Q.
    assert world_to_grid(2550, 250, 3800).startswith("Q")

    tracker = CargoTracker(harbor_seconds=600)
    cargo = {
        "id": 1,
        "type": RustMarker.CargoShipMarker,
        "type_name": "Карго",
        "x": 1500.0,
        "y": 2500.0,
        "grid": world_to_grid(1500.0, 2500.0, 4000),
    }
    first = tracker.update([cargo])
    assert any(a["kind"] == "cargo_arrival" for a in first["alerts"])
    assert first["status"]["grid"] == cargo["grid"]

    cargo2 = dict(cargo)
    cargo2["x"] = 1700.0
    cargo2["grid"] = world_to_grid(1700.0, 2500.0, 4000)
    second = tracker.update([cargo2])
    assert not any(a["kind"] == "cargo_arrival" for a in second["alerts"])

    tracker.update([])
    assert tracker._cargo_seen is False
    again = tracker.update([cargo])
    assert any(a["kind"] == "cargo_arrival" for a in again["alerts"])

    prev = [{"id": 1, "x": 100.0, "y": 100.0, "_sample_ts": 1000.0}]
    cur = [{"id": 1, "x": 200.0, "y": 150.0}]
    moved = add_motion_vectors(cur, prev, key_name="id", sample_ts=1010.0)
    assert abs(moved[0]["_vx"] - 10.0) < 1e-6
    assert abs(moved[0]["_vy"] - 5.0) < 1e-6
    assert moved[0]["_from_x"] == 100.0
    assert moved[0]["_to_x"] == 200.0
    assert moved[0]["_interp_sec"] == 10.0

    from services.rustplus.live_format import project_motion

    mid = project_motion(moved, now_ts=1015.0)[0]
    assert 100.0 < float(mid["x"]) < 200.0
    assert 100.0 < float(mid["y"]) < 150.0
    end = project_motion(moved, now_ts=1020.0)[0]
    assert abs(float(end["x"]) - 200.0) < 1e-6
    assert abs(float(end["y"]) - 150.0) < 1e-6


if __name__ == "__main__":
    test_raid()
    test_craft()
    test_furnace_multi()
    test_machine()
    test_genetics()
    test_genetics_breeding_planner()
    test_electricity()
    test_session()
    test_furnace_from_refined()
    test_cargo_live_grid_and_tracker()
    print("ALL TESTS PASSED")
