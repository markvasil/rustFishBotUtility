from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from features.shared_data import GENE_WEIGHTS, VALID_GENES


@dataclass(frozen=True)
class SlotResult:
    index: int
    center_gene: str
    result_gene: str
    explanation: str
    chance: float


def _weight(gene: str) -> float:
    return GENE_WEIGHTS.get(gene, 0.0)


def normalize_genes(text: str) -> str:
    cleaned = "".join(c.upper() for c in text if c.upper() in VALID_GENES)
    return (cleaned + "XXXXXX")[:6]


def calculate_crossbreed(
    center: str,
    top: str = "",
    bottom: str = "",
    left: str = "",
    right: str = "",
) -> Tuple[str, List[SlotResult]]:
    center_genes = normalize_genes(center)
    neighbors = [
        normalize_genes(top),
        normalize_genes(bottom),
        normalize_genes(left),
        normalize_genes(right),
    ]

    result_chars: List[str] = []
    slots: List[SlotResult] = []

    for i in range(6):
        center_gene = center_genes[i]
        center_w = _weight(center_gene)

        votes: Dict[str, float] = {}
        for neighbor in neighbors:
            gene = neighbor[i]
            votes[gene] = votes.get(gene, 0.0) + _weight(gene)

        if not votes:
            result_chars.append(center_gene)
            slots.append(
                SlotResult(
                    i + 1,
                    center_gene,
                    center_gene,
                    "Нет соседей — ген не меняется",
                    1.0,
                )
            )
            continue

        max_vote = max(votes.values())
        winners = [g for g, w in votes.items() if abs(w - max_vote) < 1e-9]

        if max_vote > center_w:
            if len(winners) == 1:
                winner = winners[0]
                chance = 1.0
                explanation = f"Доноры: {max_vote:.1f} > центр {center_w:.1f}"
            else:
                winner = winners[0]
                chance = 1.0 / len(winners)
                explanation = f"Ничья {', '.join(winners)} — шанс {chance*100:.0f}%"
            result_chars.append(winner)
        else:
            winner = center_gene
            chance = 1.0
            explanation = f"Центр {center_w:.1f} ≥ доноры {max_vote:.1f}"

        slots.append(SlotResult(i + 1, center_gene, winner, explanation, chance))

    return "".join(result_chars), slots
