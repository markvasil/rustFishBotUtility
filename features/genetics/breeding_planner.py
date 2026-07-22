"""Планировщик скрещиваний — порт логики rustbreeder.com (MIT).

Алгоритм и дефолты соответствуют
https://github.com/ryantheleach/rust-breeder
(crossbreeding.service / helper / orchestrator / Options.vue).
"""

from __future__ import annotations

import itertools
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from features.genetics.calculator import (
    _build_crossbreed_results,
    _get_winning_crossbreeding_weights,
    _planting_order_from_tie_winners,
    _requires_center_check,
    normalize_genes,
)
from features.shared_data import VALID_GENES

# ---- дефолты как в Options.vue (DEFAULT_OPTIONS) ----
MIN_CROSSBREEDING_SAPLINGS = 2
MAX_CROSSBREEDING_SAPLINGS = 5
DEFAULT_MAX_STEPS = 2  # numberOfGenerations
WITH_REPETITIONS = True
SAPLINGS_ADDED_BETWEEN_GENERATIONS = 20
MIN_TRACKED_SCORE = 4.0
MAPS_PER_GENE_LIMIT = 3  # appendAndOrganizeResults: slice(0, 3)
GENE_SCORES: Dict[str, float] = {"G": 1.0, "Y": 1.0, "H": 0.5, "W": 0.0, "X": 0.0}
# Параллелим только тяжёлые поколения (gen2+). Gen1 (~100k) быстрее в одном процессе:
# на Windows старт ProcessPool съедает больше, чем даёт параллелизм.
_PARALLEL_COMBO_THRESHOLD = 150_000
_MAX_WORKERS = max(1, min(16, (os.cpu_count() or 4)))
_PROCESS_POOL: Optional[ProcessPoolExecutor] = None


def _get_process_pool() -> ProcessPoolExecutor:
    global _PROCESS_POOL
    if _PROCESS_POOL is None:
        _PROCESS_POOL = ProcessPoolExecutor(max_workers=_MAX_WORKERS)
    return _PROCESS_POOL



@dataclass(frozen=True)
class BreedStep:
    center: Optional[str]
    crossbreeding: Tuple[str, ...]
    result: str
    chance: float
    planting_order: Tuple[Optional[int], ...] = ()

    @property
    def top(self) -> str:
        return self.crossbreeding[0] if self.crossbreeding else ""

    @property
    def bottom(self) -> str:
        return self.crossbreeding[1] if len(self.crossbreeding) > 1 else ""

    @property
    def left(self) -> str:
        return self.crossbreeding[2] if len(self.crossbreeding) > 2 else ""

    @property
    def right(self) -> str:
        return self.crossbreeding[3] if len(self.crossbreeding) > 3 else ""

    @property
    def has_planting_order(self) -> bool:
        return any(order is not None for order in self.planting_order)


@dataclass(frozen=True)
class BreedingPath:
    steps: List[BreedStep]
    final: str
    chance: float

    @property
    def step_count(self) -> int:
        return len(self.steps)


@dataclass
class _Sapling:
    genes: str
    generation_index: int = 0


@dataclass
class _GeneticsMap:
    result: str
    crossbreeding: Tuple[str, ...]
    score: float
    chance: float
    generation_index: int
    sum_of_composing_generations: int
    center: Optional[str] = None
    planting_order: Tuple[Optional[int], ...] = ()
    crossbreeding_indexes: Tuple[int, ...] = ()
    center_index: Optional[int] = None


@dataclass
class _MapGroup:
    gene: str
    maps: List[_GeneticsMap] = field(default_factory=list)


# Сырой результат воркера (pickle-friendly).
_RawMap = Tuple[
    str,  # result
    Tuple[str, ...],  # donors
    float,  # score
    float,  # chance
    int,  # composing
    Optional[str],  # center
    Tuple[Optional[int], ...],  # planting_order
    Tuple[int, ...],  # donor indexes
    Optional[int],  # center index
]


@lru_cache(maxsize=200_000)
def _weights_cached(
    crossbreeding: Tuple[str, ...],
) -> Optional[Tuple[Tuple[Tuple[str, float, Tuple[int, ...]], ...], ...]]:
    weights = _get_winning_crossbreeding_weights(crossbreeding)
    if weights is None:
        return None
    return tuple(tuple(position) for position in weights)


def parse_target_counts(values: Dict[str, int]) -> Tuple[Dict[str, int], Optional[str]]:
    counts = {gene: max(0, int(values.get(gene, 0))) for gene in sorted(VALID_GENES)}
    total = sum(counts.values())
    if total != 6:
        return counts, f"Сумма генов должна быть 6 (сейчас {total})"
    if not any(counts.values()):
        return counts, "Укажите хотя бы один ген"
    return counts, None


def gene_counts(genes: str) -> Dict[str, int]:
    normalized = normalize_genes(genes)
    return {gene: normalized.count(gene) for gene in VALID_GENES}


def matches_gene_counts(genes: str, target_counts: Dict[str, int]) -> bool:
    return gene_counts(genes) == target_counts


def sapling_score(genes: str) -> float:
    return round(sum(GENE_SCORES.get(gene, 0.0) for gene in normalize_genes(genes)), 2)


# обратная совместимость с UI
_sapling_score = sapling_score


def _unique_pool(available: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    pool: List[str] = []
    for item in available:
        gene = normalize_genes(item)
        if gene in seen:
            continue
        seen.add(gene)
        pool.append(gene)
    return pool


def _path_chance(steps: List[BreedStep]) -> float:
    chance = 1.0
    for step in steps:
        chance *= step.chance
    return chance


def _map_sort_key(item: _GeneticsMap) -> Tuple:
    """resultMapsSortingFunction — меньше = лучше."""
    return (
        item.generation_index,
        -item.chance,
        item.sum_of_composing_generations,
        len(item.crossbreeding),
        item.result,
        item.center or "",
        item.crossbreeding,
    )


def _chance_product(item: _GeneticsMap, groups: Dict[str, _MapGroup], originals: Set[str]) -> float:
    """getChanceProduct: шанс финала × шансы лучших карт родителей (gen>0)."""
    product = item.chance
    for donor in item.crossbreeding:
        if donor in originals:
            continue
        group = groups.get(donor)
        if group and group.maps:
            product *= _chance_product(group.maps[0], groups, originals)
    if item.center and item.center not in originals:
        group = groups.get(item.center)
        if group and group.maps:
            product *= _chance_product(group.maps[0], groups, originals)
    return product


def _group_sort_key(group: _MapGroup, groups: Dict[str, _MapGroup], originals: Set[str]) -> Tuple:
    """resultMapGroupsSortingFunction — меньше = лучше."""
    best = group.maps[0]
    return (
        -best.score,
        -round(_chance_product(best, groups, originals), 9),
        best.generation_index,
        best.sum_of_composing_generations,
        group.gene,
    )


def _comb(n: int, k: int) -> int:
    if k < 0 or k > n:
        return 0
    k = min(k, n - k)
    result = 1
    for i in range(k):
        result = result * (n - i) // (i + 1)
    return result


def _estimate_combo_count(n: int, mandatory_count: int, with_repetitions: bool = WITH_REPETITIONS) -> int:
    """Грубая оценка числа комбинаций (для решения о параллели)."""
    if n < MIN_CROSSBREEDING_SAPLINGS:
        return 0
    total = 0
    max_size = min(MAX_CROSSBREEDING_SAPLINGS, n) if not with_repetitions else MAX_CROSSBREEDING_SAPLINGS
    first_max = mandatory_count if mandatory_count else n
    for size in range(MIN_CROSSBREEDING_SAPLINGS, max_size + 1):
        for first in range(first_max):
            rest = size - 1
            available = n - first
            if available <= 0:
                continue
            if with_repetitions:
                if rest == 0:
                    total += 1
                else:
                    total += _comb(available + rest - 1, rest)
            else:
                if rest > available - 1:
                    continue
                total += _comb(available - 1, rest)
    return total


def _iter_combos(
    n: int,
    *,
    mandatory_count: int,
    with_repetitions: bool = WITH_REPETITIONS,
) -> Iterable[Tuple[int, ...]]:
    """Комбинации индексов без материализации всего списка (как setNextPosition)."""
    if n < MIN_CROSSBREEDING_SAPLINGS:
        return
    max_size = min(MAX_CROSSBREEDING_SAPLINGS, n) if not with_repetitions else MAX_CROSSBREEDING_SAPLINGS
    first_max = mandatory_count if mandatory_count else n
    for size in range(MIN_CROSSBREEDING_SAPLINGS, max_size + 1):
        for first in range(first_max):
            if size == 1:
                yield (first,)
                continue
            if with_repetitions:
                for rest in itertools.combinations_with_replacement(range(first, n), size - 1):
                    yield (first,) + rest
            else:
                for rest in itertools.combinations(range(first + 1, n), size - 1):
                    yield (first,) + rest


def _remember_map(groups: Dict[str, _MapGroup], item: _GeneticsMap) -> None:
    group = groups.get(item.result)
    if group is None:
        groups[item.result] = _MapGroup(item.result, [item])
        return
    maps = group.maps
    key = _map_sort_key(item)
    insert_at = len(maps)
    for index, existing in enumerate(maps):
        if key < _map_sort_key(existing):
            insert_at = index
            break
    if insert_at >= MAPS_PER_GENE_LIMIT:
        return
    maps.insert(insert_at, item)
    del maps[MAPS_PER_GENE_LIMIT:]


def _evaluate_combo(
    index_combo: Tuple[int, ...],
    source_genes: Sequence[str],
    source_gens: Sequence[int],
    source_gene_set: Set[str],
    unique_genes: Sequence[str],
    gene_to_indexes: Dict[str, List[int]],
    gene_scores: Dict[str, float],
    minimum_tracked_score: float,
) -> List[_RawMap]:
    donors = tuple(source_genes[i] for i in index_combo)
    weights_t = _weights_cached(donors)
    if weights_t is None:
        return []

    # weights_t — tuple[tuple[...]]; calculator принимает и list, и tuple.
    weights = weights_t
    donor_count = len(donors)
    out: List[_RawMap] = []

    def emit(result: str, chance: float, center: Optional[str], planting: Tuple[Optional[int], ...]) -> None:
        if result in source_gene_set:
            return
        score = round(sum(gene_scores.get(ch, 0.0) for ch in result), 2)
        if score < minimum_tracked_score:
            return
        center_index: Optional[int] = None
        if center is not None:
            combo_indexes = set(index_combo)
            for index in gene_to_indexes.get(center, ()):
                if index not in combo_indexes:
                    center_index = index
                    break
            if center_index is None:
                return
        composing = sum(source_gens[i] for i in index_combo)
        if center_index is not None:
            composing += source_gens[center_index]
        out.append(
            (
                result,
                donors,
                score,
                chance,
                composing,
                center,
                planting,
                index_combo,
                center_index,
            )
        )

    if _requires_center_check(donors, weights):  # type: ignore[arg-type]
        donor_set = set(donors)
        for center in unique_genes:
            if center in donor_set:
                continue
            partials = _build_crossbreed_results(weights, center)  # type: ignore[arg-type]
            if not partials:
                continue
            chance = 1.0 / len(partials)
            for partial in partials:
                emit(
                    "".join(partial.genes),
                    chance,
                    center,
                    _planting_order_from_tie_winners(donor_count, partial.tie_winning_indexes),
                )
    else:
        if all(len(position) == 1 for position in weights):
            result = "".join(position[0][0] for position in weights)
            emit(result, 1.0, None, tuple(None for _ in range(donor_count)))
        else:
            partials = _build_crossbreed_results(weights, None)  # type: ignore[arg-type]
            if not partials:
                return out
            chance = 1.0 / len(partials)
            for partial in partials:
                emit(
                    "".join(partial.genes),
                    chance,
                    None,
                    _planting_order_from_tie_winners(donor_count, partial.tie_winning_indexes),
                )
    return out


def _worker_simulate_range(
    payload: Tuple[
        Tuple[str, ...],
        Tuple[int, ...],
        int,  # size
        int,  # first
        int,  # second_start inclusive
        int,  # second_end exclusive
        int,  # n
        bool,  # with_repetitions
        Dict[str, float],
        float,
    ],
) -> List[_RawMap]:
    (
        source_genes,
        source_gens,
        size,
        first,
        second_start,
        second_end,
        n,
        with_repetitions,
        gene_scores,
        minimum_tracked_score,
    ) = payload
    source_gene_set = set(source_genes)
    unique_genes = list(dict.fromkeys(source_genes))
    gene_to_indexes: Dict[str, List[int]] = {}
    for index, gene in enumerate(source_genes):
        gene_to_indexes.setdefault(gene, []).append(index)

    results: List[_RawMap] = []

    def handle(combo: Tuple[int, ...]) -> None:
        results.extend(
            _evaluate_combo(
                combo,
                source_genes,
                source_gens,
                source_gene_set,
                unique_genes,
                gene_to_indexes,
                gene_scores,
                minimum_tracked_score,
            )
        )

    start = max(first, second_start)
    end = min(n, second_end)
    if size == 2:
        for second in range(start, end):
            if not with_repetitions and second <= first:
                continue
            handle((first, second))
        return results

    # size >= 3
    rest_len = size - 2
    for second in range(start, end):
        if not with_repetitions and second <= first:
            continue
        if with_repetitions:
            for rest in itertools.combinations_with_replacement(range(second, n), rest_len):
                handle((first, second) + rest)
        else:
            for rest in itertools.combinations(range(second + 1, n), rest_len):
                handle((first, second) + rest)
    return results


def _simulate_generation(
    source: List[_Sapling],
    *,
    generation_index: int,
    mandatory_count: int,
    gene_scores: Dict[str, float],
    minimum_tracked_score: float,
    groups: Dict[str, _MapGroup],
) -> None:
    """Один проход simulateCrossbreeding для текущего source."""
    n = len(source)
    if n < MIN_CROSSBREEDING_SAPLINGS:
        return

    source_genes = tuple(s.genes for s in source)
    source_gens = tuple(s.generation_index for s in source)
    source_gene_set = set(source_genes)
    unique_genes = list(dict.fromkeys(source_genes))
    gene_to_indexes: Dict[str, List[int]] = {}
    for index, gene in enumerate(source_genes):
        gene_to_indexes.setdefault(gene, []).append(index)

    estimated = _estimate_combo_count(n, mandatory_count)
    use_parallel = estimated >= _PARALLEL_COMBO_THRESHOLD and _MAX_WORKERS > 1

    def absorb(raw_maps: List[_RawMap]) -> None:
        for raw in raw_maps:
            (
                result,
                donors,
                score,
                chance,
                composing,
                center,
                planting,
                indexes,
                center_index,
            ) = raw
            _remember_map(
                groups,
                _GeneticsMap(
                    result=result,
                    crossbreeding=donors,
                    score=score,
                    chance=chance,
                    generation_index=generation_index,
                    sum_of_composing_generations=composing,
                    center=center,
                    planting_order=planting,
                    crossbreeding_indexes=indexes,
                    center_index=center_index,
                ),
            )

    if not use_parallel:
        for combo in _iter_combos(n, mandatory_count=mandatory_count):
            absorb(
                _evaluate_combo(
                    combo,
                    source_genes,
                    source_gens,
                    source_gene_set,
                    unique_genes,
                    gene_to_indexes,
                    gene_scores,
                    minimum_tracked_score,
                )
            )
        return

    max_size = (
        min(MAX_CROSSBREEDING_SAPLINGS, n) if not WITH_REPETITIONS else MAX_CROSSBREEDING_SAPLINGS
    )
    first_max = mandatory_count if mandatory_count else n
    payloads: List[
        Tuple[Tuple[str, ...], Tuple[int, ...], int, int, int, int, int, bool, Dict[str, float], float]
    ] = []

    # Режем по (size, first, second-диапазон), чтобы тяжёлые first=0 не висели в одном воркере.
    for size in range(MIN_CROSSBREEDING_SAPLINGS, max_size + 1):
        for first in range(first_max):
            second_lo = first
            second_hi = n
            span = max(1, second_hi - second_lo)
            if WITH_REPETITIONS:
                work = _comb((n - first) + (size - 1) - 1, size - 1) if size > 1 else 1
            else:
                work = _comb(n - first - 1, size - 1) if size > 1 else 1
            work_per_piece = max(8_000, estimated // max(1, _MAX_WORKERS * 4))
            pieces = max(1, min(span, (work + work_per_piece - 1) // work_per_piece))
            piece = max(1, (span + pieces - 1) // pieces)
            for sec_start in range(second_lo, second_hi, piece):
                sec_end = min(second_hi, sec_start + piece)
                payloads.append(
                    (
                        source_genes,
                        source_gens,
                        size,
                        first,
                        sec_start,
                        sec_end,
                        n,
                        WITH_REPETITIONS,
                        gene_scores,
                        minimum_tracked_score,
                    )
                )

    try:
        pool = _get_process_pool()
        futures = [pool.submit(_worker_simulate_range, payload) for payload in payloads]
        for future in as_completed(futures):
            absorb(future.result())
    except Exception:
        for payload in payloads:
            absorb(_worker_simulate_range(payload))


def _best_saplings_for_next_generation(
    source: List[_Sapling],
    groups: Dict[str, _MapGroup],
    current_generation_index: int,
    count: int,
    gene_scores: Dict[str, float],
) -> List[_Sapling]:
    """getBestSaplingsForNextGeneration."""
    maps_to_consider = [
        group.maps[0]
        for group in groups.values()
        if group.maps and group.maps[0].generation_index == current_generation_index
    ]
    if not maps_to_consider:
        return []

    column_scores = [0.0] * 6

    def add_scores(genes: str) -> None:
        for index, char in enumerate(genes):
            column_scores[index] += gene_scores.get(char, 0.0)

    for sapling in source:
        add_scores(sapling.genes)

    picked: List[_Sapling] = []
    remaining = list(maps_to_consider)
    for _ in range(min(count, len(remaining))):
        worst_to_best = sorted(range(6), key=lambda index: column_scores[index])
        subset = remaining
        for column in worst_to_best:
            best_col = max(gene_scores.get(item.result[column], 0.0) for item in subset)
            subset = [
                item
                for item in subset
                if gene_scores.get(item.result[column], 0.0) == best_col
            ]
        subset.sort(key=_map_sort_key)
        best = subset[0]
        picked.append(_Sapling(best.result, current_generation_index))
        add_scores(best.result)
        remaining = [item for item in remaining if item.result != best.result]

    return picked


def simulate_best_genetics(
    available: Iterable[str],
    *,
    max_generations: Optional[int] = None,
    gene_scores: Optional[Dict[str, float]] = None,
    minimum_tracked_score: float = MIN_TRACKED_SCORE,
    saplings_added: int = SAPLINGS_ADDED_BETWEEN_GENERATIONS,
    stop_at_max_score: bool = False,
) -> Tuple[Dict[str, _MapGroup], Set[str]]:
    """Полный прогон как CrossbreedingOrchestrator.simulateBestGenetics.

    stop_at_max_score: для «Найти лучший» — не считать следующие поколения,
    если уже есть результат с максимальным возможным score.
    """
    originals = _unique_pool(available)
    if not originals:
        return {}, set()

    scores = gene_scores or GENE_SCORES
    generation_limit = max_generations if max_generations is not None else DEFAULT_MAX_STEPS
    source = [_Sapling(gene, 0) for gene in originals]
    groups: Dict[str, _MapGroup] = {}
    original_set = set(originals)
    max_possible_score = round(6.0 * max(scores.values()) if scores else 6.0, 2)

    for generation_index in range(1, generation_limit + 1):
        mandatory = 0
        if generation_index > 1:
            for sapling in source:
                if sapling.generation_index == generation_index - 1:
                    mandatory += 1
                else:
                    break

        _simulate_generation(
            source,
            generation_index=generation_index,
            mandatory_count=mandatory,
            gene_scores=scores,
            minimum_tracked_score=minimum_tracked_score,
            groups=groups,
        )

        if stop_at_max_score and groups:
            best = max((group.maps[0].score for group in groups.values() if group.maps), default=0.0)
            if best + 1e-9 >= max_possible_score:
                break

        if generation_index >= generation_limit:
            break

        additional = _best_saplings_for_next_generation(
            source,
            groups,
            generation_index,
            saplings_added,
            scores,
        )
        if not additional:
            break
        source = additional + source

    return groups, original_set


def _step_required_genes(step: BreedStep, pool_set: Set[str]) -> Set[str]:
    needed = set(step.crossbreeding)
    if step.center:
        needed.add(step.center)
    return {gene for gene in needed if gene not in pool_set}


def _merge_prerequisite_paths(
    bred_parents: Iterable[str],
    pool_set: Set[str],
    paths_to: Dict[str, List[BreedStep]],
) -> Optional[List[BreedStep]]:
    unique_parents = sorted(set(bred_parents))
    if not unique_parents:
        return []

    pending_steps: List[BreedStep] = []
    seen_steps: Set[Tuple[Optional[str], Tuple[str, ...], str]] = set()
    for gene in unique_parents:
        path = paths_to.get(gene)
        if not path:
            return None
        for step in path:
            key = (step.center, step.crossbreeding, step.result)
            if key in seen_steps:
                continue
            seen_steps.add(key)
            pending_steps.append(step)

    merged: List[BreedStep] = []
    available = set(pool_set)
    remaining = list(pending_steps)
    while remaining:
        progress = False
        for index, step in enumerate(remaining):
            if not _step_required_genes(step, pool_set).issubset(available):
                continue
            merged.append(step)
            available.add(step.result)
            remaining.pop(index)
            progress = True
            break
        if not progress:
            return None

    if not set(unique_parents).issubset(available):
        return None
    return merged


def _paths_from_groups(
    groups: Dict[str, _MapGroup],
    originals: Set[str],
) -> Dict[str, List[BreedStep]]:
    """Строит лучший путь к каждому гену из map groups (linkGenerationTree упрощённо)."""
    paths_to: Dict[str, List[BreedStep]] = {gene: [] for gene in originals}

    ordered = sorted(
        groups.values(),
        key=lambda group: (group.maps[0].generation_index if group.maps else 99, group.gene),
    )
    for group in ordered:
        if not group.maps:
            continue
        best = group.maps[0]
        step = BreedStep(
            best.center,
            best.crossbreeding,
            best.result,
            best.chance,
            best.planting_order,
        )
        parents = set(best.crossbreeding)
        if best.center:
            parents.add(best.center)
        bred = [gene for gene in parents if gene not in originals]
        base = _merge_prerequisite_paths(bred, originals, paths_to)
        if base is None:
            if not all(gene in originals or gene in paths_to for gene in parents):
                continue
            base = _merge_prerequisite_paths(bred, originals, paths_to)
            if base is None:
                continue
        paths_to[group.gene] = base + [step]

    return paths_to


def _sorted_groups(
    groups: Dict[str, _MapGroup],
    originals: Set[str],
) -> List[_MapGroup]:
    return sorted(
        (group for group in groups.values() if group.maps),
        key=lambda group: _group_sort_key(group, groups, originals),
    )


def _breeding_path_from_map(
    item: _GeneticsMap,
    paths_to: Dict[str, List[BreedStep]],
    originals: Set[str],
) -> Optional[BreedingPath]:
    step = BreedStep(
        item.center,
        item.crossbreeding,
        item.result,
        item.chance,
        item.planting_order,
    )
    parents = set(item.crossbreeding)
    if item.center:
        parents.add(item.center)
    bred = [gene for gene in parents if gene not in originals]
    base = _merge_prerequisite_paths(bred, originals, paths_to)
    if base is None:
        return None
    steps = base + [step]
    return BreedingPath(steps, item.result, _path_chance(steps))


def find_breeding_paths(
    available: Iterable[str],
    target_counts: Dict[str, int],
    *,
    max_steps: Optional[int] = None,
    max_paths: int = 8,
) -> Tuple[List[BreedingPath], Optional[str]]:
    pool = _unique_pool(available)
    if not pool:
        return [], "Сначала отсканируйте или введите гены"

    _, error = parse_target_counts(target_counts)
    if error:
        return [], error

    direct: List[BreedingPath] = []
    for gene in sorted(pool):
        if matches_gene_counts(gene, target_counts):
            direct.append(BreedingPath([], gene, 1.0))
    if direct:
        return direct[:max_paths], None

    generation_limit = max_steps if max_steps is not None else DEFAULT_MAX_STEPS
    groups, originals = simulate_best_genetics(pool, max_generations=generation_limit)
    paths_to = _paths_from_groups(groups, originals)

    matched: List[BreedingPath] = []
    for group in _sorted_groups(groups, originals):
        if not matches_gene_counts(group.gene, target_counts):
            continue
        for item in group.maps:
            path = _breeding_path_from_map(item, paths_to, originals)
            if path is None:
                continue
            matched.append(path)
            break
        if len(matched) >= max_paths:
            break

    if not matched:
        return [], (
            f"Пути не найдены за {generation_limit} поколений с {len(pool)} генами. "
            "Попробуйте добавить растения ближе к цели или увеличить глубину поиска."
        )
    return matched[:max_paths], None


def find_best_plant(
    available: Iterable[str],
    *,
    max_steps: Optional[int] = None,
    max_paths: int = 3,
) -> Tuple[List[BreedingPath], Optional[str]]:
    """Топ результатов как на rustbreeder: разные гены, отсортированные map groups."""
    pool = _unique_pool(available)
    if not pool:
        return [], "Сначала отсканируйте или введите гены"

    generation_limit = max_steps if max_steps is not None else DEFAULT_MAX_STEPS
    groups, originals = simulate_best_genetics(
        pool,
        max_generations=generation_limit,
        stop_at_max_score=True,
    )
    if not groups:
        return [], "Не удалось ничего вывести из этих генов"

    paths_to = _paths_from_groups(groups, originals)
    sorted_groups = _sorted_groups(groups, originals)
    if not sorted_groups:
        return [], "Не удалось ничего вывести из этих генов"

    best_score = sorted_groups[0].maps[0].score
    result_paths: List[BreedingPath] = []
    for group in sorted_groups:
        if abs(group.maps[0].score - best_score) > 1e-9:
            break
        path = _breeding_path_from_map(group.maps[0], paths_to, originals)
        if path is None:
            if group.gene in originals:
                path = BreedingPath([], group.gene, 1.0)
            else:
                continue
        result_paths.append(path)
        if len(result_paths) >= max_paths:
            break

    if not result_paths:
        return [], "Не удалось ничего вывести из этих генов"
    return result_paths, None


def format_gene_profile(counts: Dict[str, int]) -> str:
    parts = [f"{count}{gene}" for gene, count in counts.items() if count > 0]
    return " ".join(parts) if parts else "—"
