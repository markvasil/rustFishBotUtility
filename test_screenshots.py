"""Проверка распознавания генов на всех эталонных скриншотах."""
from __future__ import annotations

import re
import sys
from pathlib import Path

from PIL import Image

import features.genetics.scanner as scanner_module
from features.genetics.calibration import RegionCalibration
from features.genetics.scanner import get_regions_for_frame, scan_frame_for_genes

SCREENSHOT_DIR = Path(__file__).resolve().parent / "screenshot"
EXPECTED_OVERRIDES: dict[str, str] = {
    "23.jpg": "WYGXGH",
}


def expected_genes_from_filename(filename: str) -> str | None:
    if filename in EXPECTED_OVERRIDES:
        return EXPECTED_OVERRIDES[filename]
    match = re.match(r"^([WYGHX]+)(?:_\d+)?$", Path(filename).stem)
    return match.group(1) if match else None


def collect_cases() -> list[tuple[Path, str]]:
    cases: list[tuple[Path, str]] = []
    for path in sorted(SCREENSHOT_DIR.glob("*.jpg")):
        expected = expected_genes_from_filename(path.name)
        if expected and len(expected) == 6:
            cases.append((path, expected))
    return cases


def run_checks() -> int:
    region = get_regions_for_frame(2560, 1440)["inventory"]
    cases = collect_cases()
    if not cases:
        print("Нет скриншотов в screenshot/")
        return 1

    original_detect = scanner_module._detect_gene_row_centers
    failures = 0
    total_checks = 0

    print(f"Скриншотов: {len(cases)}, проверок на файл: 5, всего: {len(cases) * 5}")
    print("-" * 72)

    for path, expected in cases:
        frame = Image.open(path).convert("RGB")
        if frame.size != (2560, 1440):
            print(f"FAIL {path.name}: размер {frame.size}, нужен 2560x1440")
            failures += 5
            total_checks += 5
            continue

        checks = [
            ("auto", lambda: scan_frame_for_genes(
                frame, region, profile_id="1440p", calibration=RegionCalibration()
            )),
            ("default", lambda: scan_frame_for_genes(
                frame, region, profile_id="1440p", calibration=None
            )),
        ]

        scanner_module._detect_gene_row_centers = lambda _frame, _region: None
        checks.append(("fallback", lambda: scan_frame_for_genes(
            frame, region, profile_id="1440p", calibration=RegionCalibration()
        )))
        scanner_module._detect_gene_row_centers = original_detect

        checks.extend([
            ("repeat1", lambda: scan_frame_for_genes(
                frame, region, profile_id="1440p", calibration=RegionCalibration()
            )),
            ("repeat2", lambda: scan_frame_for_genes(
                frame, region, profile_id="1440p", calibration=RegionCalibration()
            )),
        ])

        file_ok = True
        for mode, run in checks:
            total_checks += 1
            got = run()
            if got != expected:
                file_ok = False
                failures += 1
                print(f"FAIL {path.name:20} [{mode:8}] expected={expected} got={got}")

        if file_ok:
            print(f"OK   {path.name:20} -> {expected} (5/5)")

    print("-" * 72)
    passed = total_checks - failures
    print(f"Итого: {passed}/{total_checks} OK, ошибок: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run_checks())
