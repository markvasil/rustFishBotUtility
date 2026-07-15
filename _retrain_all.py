"""Rebuild templates from all screenshots and evaluate."""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

from features.genetics.calibration import RegionCalibration
from features.genetics.scanner import (
    SLOT_HALF_H_MIN,
    SLOT_HALF_W_MIN,
    _classify_slot_from_frame,
    _detect_gene_row_centers,
    _extract_gene_letter_patch,
    _genes_from_slot_rects,
    _jaccard_similarity,
    _slot_centers,
    _slot_crop_sizes,
    _slot_rects_from_centers,
    get_regions_for_frame,
    scan_frame_for_genes,
)

ROOT = Path("screenshot")
VALID = set("WYGHX")


def expected_from_name(name: str) -> str | None:
    overrides = {"23.jpg": "WYGXGH"}
    if name in overrides:
        return overrides[name]
    stem = Path(name).stem
    match = re.match(r"^([WYGHX]+)(?:_\d+)?$", stem)
    return match.group(1) if match else None


def slot_rects_for_frame(frame: Image.Image, region) -> list[tuple[int, int, int, int]] | None:
    width, height = frame.size
    half_w, half_h = _slot_crop_sizes(width, height, region)
    detected = _detect_gene_row_centers(frame, region)
    if detected and len(detected) == 6:
        return _slot_rects_from_centers(detected, half_w, half_h)
    centers = _slot_centers(width, height, region, RegionCalibration())
    return _slot_rects_from_centers(centers, half_w, half_h)


def patch_to_rows(patch: np.ndarray) -> list[str]:
    return ["".join("#" if value > 0.5 else "." for value in row) for row in patch]


def rows_to_patch(rows: list[str]) -> np.ndarray:
    width = max(len(row) for row in rows)
    normalized = [row.ljust(width, ".")[:width] for row in rows]
    return np.array([[1 if ch == "#" else 0 for ch in row] for row in normalized], dtype=np.float32)


def collect_cases() -> list[tuple[Path, str]]:
    cases: list[tuple[Path, str]] = []
    for path in sorted(ROOT.glob("*.jpg")):
        expected = expected_from_name(path.name)
        if not expected or len(expected) != 6:
            continue
        cases.append((path, expected))
    return cases


def build_templates(cases: list[tuple[Path, str]], region) -> dict[str, list[np.ndarray]]:
    templates: dict[str, list[np.ndarray]] = {gene: [] for gene in VALID}
    seen: set[tuple[str, tuple[str, ...]]] = set()

    for path, expected in cases:
        frame = Image.open(path).convert("RGB")
        if frame.size != (2560, 1440):
            continue
        rects = slot_rects_for_frame(frame, region)
        if not rects:
            continue
        for index, rect in enumerate(rects):
            gene = expected[index]
            slot = np.array(frame.crop(rect))
            patch = _extract_gene_letter_patch(slot)
            if patch is None:
                continue
            key = (gene, tuple(patch_to_rows(patch)))
            if key in seen:
                continue
            seen.add(key)
            templates[gene].append(patch)
    return templates


def classify_patch(patch: np.ndarray, templates: dict[str, list[np.ndarray]]) -> str | None:
    scores: list[tuple[str, float]] = []
    for gene, gene_templates in templates.items():
        if not gene_templates:
            continue
        scores.append((gene, max(_jaccard_similarity(patch, template) for template in gene_templates)))
    scores.sort(key=lambda item: -item[1])
    if not scores or scores[0][1] < 0.28:
        return None
    if len(scores) > 1 and scores[0][1] - scores[1][1] < 0.04:
        return None
    return scores[0][0]


def evaluate(cases: list[tuple[Path, str]], templates: dict[str, list[np.ndarray]], region) -> list[tuple[str, str, str]]:
    failures: list[tuple[str, str, str]] = []
    for path, expected in cases:
        frame = Image.open(path).convert("RGB")
        if frame.size != (2560, 1440):
            continue
        rects = slot_rects_for_frame(frame, region)
        if not rects:
            failures.append((path.name, expected, "NO_RECTS"))
            continue
        got = ""
        for rect in rects:
            patch = _extract_gene_letter_patch(np.array(frame.crop(rect)))
            gene = classify_patch(patch, templates) if patch is not None else None
            got += gene or "?"
        if got != expected:
            failures.append((path.name, expected, got))
    return failures


if __name__ == "__main__":
    region = get_regions_for_frame(2560, 1440)["inventory"]
    cases = collect_cases()
    templates = build_templates(cases, region)
    for gene in sorted(VALID):
        print(gene, len(templates[gene]))
    failures = evaluate(cases, templates, region)
    print(f"failures {len(failures)}/{len(cases)}")
    for item in failures:
        print("FAIL", *item)
