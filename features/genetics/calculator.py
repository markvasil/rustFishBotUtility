from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from features.shared_data import GENE_WEIGHTS, VALID_GENES

RED_GENE_WEIGHT = 1.0


@dataclass(frozen=True)
class SlotResult:
    index: int
    center_gene: str
    result_gene: str
    explanation: str
    chance: float


@dataclass(frozen=True)
class CrossbreedOutcome:
    result: str
    chance: float
    center: Optional[str]
    crossbreeding: Tuple[str, ...]


def _weight(gene: str) -> float:
    return GENE_WEIGHTS.get(gene, 0.0)


def normalize_genes(text: str) -> str:
    cleaned = "".join(c.upper() for c in text if c.upper() in VALID_GENES)
    return (cleaned + "XXXXXX")[:6]


def crossbreed_success_chance(slots: List[SlotResult]) -> float:
    chance = 1.0
    for slot in slots:
        chance *= slot.chance
    return chance


def _get_winning_crossbreeding_weights(
    crossbreeding: Tuple[str, ...],
) -> Optional[List[List[Tuple[str, float, Tuple[int, ...]]]]]:
    """Возвращает победителей по каждому слоту или None, если комбинация отбрасывается."""
    normalized = tuple(normalize_genes(item) for item in crossbreeding)
    all_positions: List[List[Tuple[str, float, Tuple[int, ...]]]] = []
    contributed: set[int] = set()
    early_ties = 0

    for position in range(6):
        details: Dict[str, List[float | List[int]]] = {}
        for index, sapling in enumerate(normalized):
            gene = sapling[position]
            if gene not in details:
                details[gene] = [0.0, []]
            details[gene][0] = float(details[gene][0]) + _weight(gene)
            contributors = details[gene][1]
            assert isinstance(contributors, list)
            contributors.append(index)

        max_vote = max(float(value[0]) for value in details.values())
        winners = [
            (gene, float(value[0]), tuple(value[1]))
            for gene, value in details.items()
            if abs(float(value[0]) - max_vote) < 1e-9
        ]

        if len(winners) > 1 and max_vote > RED_GENE_WEIGHT:
            early_ties += 1
        if early_ties > 1:
            return None

        all_positions.append(winners)
        for _, _, indexes in winners:
            contributed.update(indexes)

    if len(contributed) != len(normalized):
        return None
    return all_positions


def _requires_center_check(
    crossbreeding: Tuple[str, ...],
    weights: List[List[Tuple[str, float, Tuple[int, ...]]]],
) -> bool:
    if len(crossbreeding) > 5:
        return False
    return any(position_winners[0][1] <= RED_GENE_WEIGHT for position_winners in weights)


def _build_crossbreed_results(
    weights: List[List[Tuple[str, float, Tuple[int, ...]]]],
    center: Optional[str] = None,
) -> List[str]:
    center_genes = normalize_genes(center) if center else None
    partial_results: List[List[str]] = [[]]
    definitive_ties = 0

    for position, position_winners in enumerate(weights):
        donor_max = position_winners[0][1]
        use_center = (
            center_genes is not None
            and _weight(center_genes[position]) >= donor_max
        )
        next_partial: List[List[str]] = []

        if use_center:
            assert center_genes is not None
            for partial in partial_results:
                next_partial.append(partial + [center_genes[position]])
        elif len(position_winners) == 1:
            gene = position_winners[0][0]
            for partial in partial_results:
                next_partial.append(partial + [gene])
        else:
            definitive_ties += 1
            if definitive_ties > 1:
                return []
            for gene, _, _ in position_winners:
                for partial in partial_results:
                    next_partial.append(partial + [gene])

        partial_results = next_partial

    return ["".join(chars) for chars in partial_results]


def crossbreed_combination(
    crossbreeding: Tuple[str, ...],
    source_pool: Tuple[str, ...],
) -> List[CrossbreedOutcome]:
    """Модель скрещивания как на rustbreeder.com."""
    if len(crossbreeding) < 2:
        return []

    weights = _get_winning_crossbreeding_weights(crossbreeding)
    if weights is None:
        return []

    normalized_pool = tuple(normalize_genes(item) for item in source_pool)
    normalized_combo = tuple(normalize_genes(item) for item in crossbreeding)
    outcomes: List[CrossbreedOutcome] = []

    if _requires_center_check(crossbreeding, weights):
        others = [gene for gene in normalized_pool if gene not in normalized_combo]
        for center in others:
            for result in _build_crossbreed_results(weights, center):
                outcomes.append(
                    CrossbreedOutcome(
                        result=result,
                        chance=0.0,
                        center=center,
                        crossbreeding=normalized_combo,
                    )
                )
    else:
        for result in _build_crossbreed_results(weights):
            outcomes.append(
                CrossbreedOutcome(
                    result=result,
                    chance=0.0,
                    center=None,
                    crossbreeding=normalized_combo,
                )
            )

    if not outcomes:
        return []

    per_combo_chance = 1.0 / len(outcomes)
    return [
        CrossbreedOutcome(
            result=item.result,
            chance=per_combo_chance,
            center=item.center,
            crossbreeding=item.crossbreeding,
        )
        for item in outcomes
    ]


def calculate_crossbreed(
    center: str,
    top: str = "",
    bottom: str = "",
    left: str = "",
    right: str = "",
) -> Tuple[str, List[SlotResult]]:
    result, slots, _chance = calculate_crossbreed_planter(
        center,
        (
            normalize_genes(top),
            normalize_genes(bottom),
            normalize_genes(left),
            normalize_genes(right),
        ),
    )
    return result, slots


def calculate_crossbreed_planter(
    center: str,
    surrounding: Tuple[str, ...],
) -> Tuple[str, List[SlotResult], float]:
    center_genes = normalize_genes(center)
    neighbors = [normalize_genes(item) for item in surrounding if item]

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
                explanation = f"Ничья {', '.join(winners)} — шанс {chance * 100:.0f}%"
            result_chars.append(winner)
        else:
            winner = center_gene
            chance = 1.0
            explanation = f"Центр {center_w:.1f} ≥ доноры {max_vote:.1f}"

        slots.append(SlotResult(i + 1, center_gene, winner, explanation, chance))

    return "".join(result_chars), slots, crossbreed_success_chance(slots)
