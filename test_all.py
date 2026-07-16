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


def test_genetics_calibration():
    from features.genetics.calibration import (
        RegionCalibration,
        load_calibrations,
        profile_key,
        save_calibrations,
    )

    data: dict = {}
    cal = RegionCalibration(
        dx=0,
        dy=0,
        slots=((10, 0), (5, 0), (0, 0), (0, 0), (0, 0), (0, 0)),
    )
    save_calibrations(data, "1440p", {"inventory": cal})
    loaded = load_calibrations(data, "1440p", ["inventory"])
    assert loaded["inventory"].slots[0] == (10, 0)
    assert loaded["inventory"].slots[1] == (5, 0)
    assert profile_key(None, "2K") == "1440p"


def test_genetics_scanner():
    import numpy as np
    from PIL import Image

    from features.genetics.scanner import (
        RESOLUTION_PROFILES,
        SCAN_REGIONS,
        classify_gene_slot,
        get_regions_for_frame,
        normalize_capture_frame,
        resolve_profile,
    )

    green = np.full((48, 40, 3), (50, 170, 70), dtype=np.uint8)
    yellow = np.full((48, 40, 3), (220, 180, 40), dtype=np.uint8)
    assert classify_gene_slot(green) is None
    assert classify_gene_slot(yellow) is None

    from features.genetics.calibration import RegionCalibration
    from features.genetics.scanner import calibrated_slot_rects

    region = SCAN_REGIONS["inventory"]
    cal = RegionCalibration(
        0,
        0,
        ((0, 0), (20, 0), (40, 0), (60, 0), (80, 0), (100, 0)),
    )
    rects = calibrated_slot_rects(2560, 1440, region, cal)
    widths = [rect[2] - rect[0] for rect in rects]
    assert all(width == widths[0] for width in widths)
    assert widths[0] >= 20

    frame = Image.new("RGB", (1920, 1080), (20, 20, 20))
    assert normalize_capture_frame(frame).size == (1920, 1080)
    assert "planter" in SCAN_REGIONS

    assert resolve_profile(1920, 1080).id == "1080p"
    assert resolve_profile(2560, 1440).id == "1440p"
    assert resolve_profile(2560, 1440, "1080p").id == "1080p"
    assert len(get_regions_for_frame(2560, 1440)) == len(RESOLUTION_PROFILES["1440p"].regions)

    import re

    import features.genetics.scanner as scanner_module

    from features.genetics.scanner import scan_frame_for_genes

    screenshot_dir = Path(__file__).resolve().parent / "screenshot"
    expected_overrides = {"23.jpg": "WYGXGH"}

    def expected_genes_from_filename(filename: str) -> str | None:
        if filename in expected_overrides:
            return expected_overrides[filename]
        match = re.match(r"^([WYGHX]+)(?:_\d+)?$", Path(filename).stem)
        return match.group(1) if match else None

    cases: list[tuple[Path, str]] = []
    for path in sorted(screenshot_dir.glob("*.jpg")):
        expected = expected_genes_from_filename(path.name)
        if expected and len(expected) == 6:
            cases.append((path, expected))
    assert cases, "Нет эталонных скриншотов в screenshot/"

    region = get_regions_for_frame(2560, 1440)["inventory"]
    original_detect = scanner_module._detect_gene_row_centers

    for path, expected in cases:
        frame = Image.open(path).convert("RGB")
        assert frame.size == (2560, 1440), f"{path.name}: ожидается 2560×1440"

        genes = scan_frame_for_genes(
            frame,
            region,
            profile_id="1440p",
            calibration=RegionCalibration(),
        )
        assert genes == expected, f"{path.name} auto: expected {expected}, got {genes}"

        genes = scan_frame_for_genes(
            frame,
            region,
            profile_id="1440p",
            calibration=None,
        )
        assert genes == expected, f"{path.name} default: expected {expected}, got {genes}"

        try:
            scanner_module._detect_gene_row_centers = lambda _frame, _region: None
            genes = scan_frame_for_genes(
                frame,
                region,
                profile_id="1440p",
                calibration=RegionCalibration(),
            )
            assert genes == expected, f"{path.name} fallback: expected {expected}, got {genes}"
        finally:
            scanner_module._detect_gene_row_centers = original_detect

        for attempt in range(2):
            genes = scan_frame_for_genes(
                frame,
                region,
                profile_id="1440p",
                calibration=RegionCalibration(),
            )
            assert genes == expected, (
                f"{path.name} repeat {attempt + 1}: expected {expected}, got {genes}"
            )


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


if __name__ == "__main__":
    test_raid()
    test_craft()
    test_furnace_multi()
    test_machine()
    test_genetics()
    test_genetics_breeding_planner()
    test_genetics_calibration()
    test_genetics_scanner()
    test_electricity()
    test_session()
    test_furnace_from_refined()
    print("ALL TESTS PASSED")
