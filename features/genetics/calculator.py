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
    # Индексы соседей (0-based в surrounding), дающих result_gene при ничьей.
    tie_winner_neighbor_indexes: Tuple[int, ...] = ()


@dataclass(frozen=True)
class CrossbreedOutcome:
    result: str
    chance: float
    center: Optional[str]
    crossbreeding: Tuple[str, ...]
    # Порядок посадки доноров при шансе <100% (как 1st/2nd на rustbreeder.com).
    # planting_order[i] — метка 1, 2, … для crossbreeding[i], либо None.
    planting_order: Tuple[Optional[int], ...] = ()


@dataclass(frozen=True)
class _PartialCrossbreedResult:
    genes: List[str]
    tie_winning_indexes: Optional[Tuple[int, ...]] = None
    tie_losing_indexes: Optional[Tuple[int, ...]] = None


def _weight(gene: str) -> float:
    return GENE_WEIGHTS.get(gene, 0.0)


def _planting_order_from_tie_winners(
    donor_count: int,
    tie_winning_indexes: Optional[Tuple[int, ...]],
) -> Tuple[Optional[int], ...]:
    """Метки 1st/2nd/… для доноров, дающих нужный ген в ничьей (гайд rustbreeder)."""
    if not tie_winning_indexes:
        return tuple(None for _ in range(donor_count))
    labels: List[Optional[int]] = [None] * donor_count
    for order, index in enumerate(tie_winning_indexes, start=1):
        if 0 <= index < donor_count and labels[index] is None:
            labels[index] = order
    return tuple(labels)


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
) -> List[_PartialCrossbreedResult]:
    center_genes = normalize_genes(center) if center else None
    partial_results: List[_PartialCrossbreedResult] = [_PartialCrossbreedResult(genes=[])]
    definitive_ties = 0

    for position, position_winners in enumerate(weights):
        donor_max = position_winners[0][1]
        use_center = (
            center_genes is not None
            and _weight(center_genes[position]) >= donor_max
        )
        next_partial: List[_PartialCrossbreedResult] = []

        if use_center:
            assert center_genes is not None
            for partial in partial_results:
                next_partial.append(
                    _PartialCrossbreedResult(
                        genes=partial.genes + [center_genes[position]],
                        tie_winning_indexes=partial.tie_winning_indexes,
                        tie_losing_indexes=partial.tie_losing_indexes,
                    )
                )
        elif len(position_winners) == 1:
            gene = position_winners[0][0]
            for partial in partial_results:
                next_partial.append(
                    _PartialCrossbreedResult(
                        genes=partial.genes + [gene],
                        tie_winning_indexes=partial.tie_winning_indexes,
                        tie_losing_indexes=partial.tie_losing_indexes,
                    )
                )
        else:
            definitive_ties += 1
            if definitive_ties > 1:
                return []
            for gene, _, winner_indexes in position_winners:
                loser_indexes: List[int] = []
                for other_gene, _, other_indexes in position_winners:
                    if other_gene != gene:
                        loser_indexes.extend(other_indexes)
                for partial in partial_results:
                    next_partial.append(
                        _PartialCrossbreedResult(
                            genes=partial.genes + [gene],
                            tie_winning_indexes=tuple(winner_indexes),
                            tie_losing_indexes=tuple(loser_indexes),
                        )
                    )

        partial_results = next_partial

    return partial_results


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
    donor_count = len(normalized_combo)

    if _requires_center_check(crossbreeding, weights):
        others = [gene for gene in normalized_pool if gene not in normalized_combo]
        for center in others:
            for partial in _build_crossbreed_results(weights, center):
                outcomes.append(
                    CrossbreedOutcome(
                        result="".join(partial.genes),
                        chance=0.0,
                        center=center,
                        crossbreeding=normalized_combo,
                        planting_order=_planting_order_from_tie_winners(
                            donor_count, partial.tie_winning_indexes
                        ),
                    )
                )
    else:
        for partial in _build_crossbreed_results(weights):
            outcomes.append(
                CrossbreedOutcome(
                    result="".join(partial.genes),
                    chance=0.0,
                    center=None,
                    crossbreeding=normalized_combo,
                    planting_order=_planting_order_from_tie_winners(
                        donor_count, partial.tie_winning_indexes
                    ),
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
            planting_order=item.planting_order,
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


def planting_order_for_planter(
    surrounding: Tuple[str, ...],
    slots: List[SlotResult],
) -> Tuple[Optional[int], ...]:
    """Метки 1st/2nd для соседей грядки при ничьей (гайд rustbreeder Example 4)."""
    neighbors = [normalize_genes(item) for item in surrounding if item]
    donor_count = len(neighbors)
    if donor_count == 0:
        return ()

    for slot in slots:
        if slot.chance >= 0.9999 or not slot.tie_winner_neighbor_indexes:
            continue
        return _planting_order_from_tie_winners(donor_count, slot.tie_winner_neighbor_indexes)
    return tuple(None for _ in range(donor_count))


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
        contributors: Dict[str, List[int]] = {}
        for neighbor_index, neighbor in enumerate(neighbors):
            gene = neighbor[i]
            votes[gene] = votes.get(gene, 0.0) + _weight(gene)
            contributors.setdefault(gene, []).append(neighbor_index)

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
                tie_winners: Tuple[int, ...] = ()
            else:
                winner = winners[0]
                chance = 1.0 / len(winners)
                explanation = f"Ничья {', '.join(winners)} — шанс {chance * 100:.0f}%"
                tie_winners = tuple(contributors.get(winner, []))
            result_chars.append(winner)
        else:
            winner = center_gene
            chance = 1.0
            explanation = f"Центр {center_w:.1f} >= доноры {max_vote:.1f}"
            tie_winners = ()

        slots.append(
            SlotResult(
                i + 1,
                center_gene,
                winner,
                explanation,
                chance,
                tie_winners,
            )
        )

    return "".join(result_chars), slots, crossbreed_success_chance(slots)
