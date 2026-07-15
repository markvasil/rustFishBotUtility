from __future__ import annotations

from typing import Dict, List

import numpy as np

from features.genetics.letter_templates_data import _GENE_LETTER_TEMPLATE_ROWS


def _patch_from_rows(rows: List[str]) -> np.ndarray:
    width = max(len(row) for row in rows)
    normalized = [row.ljust(width, ".")[:width] for row in rows]
    return np.array([[1 if ch == "#" else 0 for ch in row] for row in normalized], dtype=np.float32)


GENE_LETTER_TEMPLATES: Dict[str, List[np.ndarray]] = {
    gene: [_patch_from_rows(rows) for rows in templates]
    for gene, templates in _GENE_LETTER_TEMPLATE_ROWS.items()
}
