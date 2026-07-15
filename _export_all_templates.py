"""Export deduplicated letter templates from screenshot folder."""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
from PIL import Image

from features.genetics.calibration import RegionCalibration
from features.genetics.scanner import (
    _detect_gene_row_centers,
    _extract_gene_letter_patch,
    _jaccard_similarity,
    _slot_centers,
    _slot_crop_sizes,
    _slot_rects_from_centers,
    get_regions_for_frame,
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


def patch_to_rows(patch: np.ndarray) -> list[str]:
    return ["".join("#" if value > 0.5 else "." for value in row) for row in patch]


def dedupe_templates(templates: list[np.ndarray], min_gap: float = 0.02) -> list[np.ndarray]:
    kept: list[np.ndarray] = []
    for patch in templates:
        if any(_jaccard_similarity(patch, existing) >= 1.0 - min_gap for existing in kept):
            continue
        kept.append(patch)
    return kept


def main() -> None:
    region = get_regions_for_frame(2560, 1440)["inventory"]
    buckets: dict[str, list[np.ndarray]] = {gene: [] for gene in sorted(VALID)}

    for path in sorted(ROOT.glob("*.jpg")):
        expected = expected_from_name(path.name)
        if not expected or len(expected) != 6:
            continue
        frame = Image.open(path).convert("RGB")
        if frame.size != (2560, 1440):
            continue
        width, height = frame.size
        half_w, half_h = _slot_crop_sizes(width, height, region)
        detected = _detect_gene_row_centers(frame, region)
        if detected and len(detected) == 6:
            rects = _slot_rects_from_centers(detected, half_w, half_h)
        else:
            centers = _slot_centers(width, height, region, RegionCalibration())
            rects = _slot_rects_from_centers(centers, half_w, half_h)
        for index, rect in enumerate(rects):
            patch = _extract_gene_letter_patch(np.array(frame.crop(rect)))
            if patch is not None:
                buckets[expected[index]].append(patch)

    print("_GENE_LETTER_TEMPLATE_ROWS: dict[str, list[list[str]]] = {")
    for gene in sorted(VALID):
        unique = dedupe_templates(buckets[gene])
        print(f'    "{gene}": [')
        for patch in unique:
            print("        [")
            for row in patch_to_rows(patch):
                print(f'            "{row}",')
            print("        ],")
        print("    ],")
        print(f"# {gene}: {len(unique)} templates", file=__import__("sys").stderr)
    print("}")


if __name__ == "__main__":
    main()
