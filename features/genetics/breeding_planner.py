"""Планировщик скрещиваний — порт логики rustbreeder.com (MIT).

Алгоритм и дефолты соответствуют
https://github.com/ryantheleach/rust-breeder
(crossbreeding.service / helper / orchestrator / Options.vue).
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from features.genetics.calculator import crossbreed_combination, normalize_genes
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
    # индексы в source-списке (для object-identity центров как у rustbreeder)
    crossbreeding_indexes: Tuple[int, ...] = ()
    center_index: Optional[int] = None


@dataclass
class _MapGroup:
    gene: str
    maps: List[_GeneticsMap] = field(default_factory=list)


@lru_cache(maxsize=200_000)
def _breed_combo_cached(
    crossbreeding: Tuple[str, ...],
    source_pool: Tuple[str, ...],
) -> Tuple[Tuple[str, Optional[str], float, Tuple[Optional[int], ...]], ...]:
    outcomes = crossbreed_combination(crossbreeding, source_pool)
    return tuple(
        (item.result, item.center, item.chance, item.planting_order) for item in outcomes
    )


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


def _collect_combos(
    source: Sequence[_Sapling],
    *,
    mandatory_count: int,
    with_repetitions: bool = WITH_REPETITIONS,
) -> List[Tuple[int, ...]]:
    """Комбинации индексов; при mandatory_count>0 каждая включает ≥1 из [0..mandatory)."""
    n = len(source)
    if n < MIN_CROSSBREEDING_SAPLINGS:
        return []

    combos: List[Tuple[int, ...]] = []
    max_size = min(MAX_CROSSBREEDING_SAPLINGS, n) if not with_repetitions else MAX_CROSSBREEDING_SAPLINGS
    indexes = range(n)
    for size in range(MIN_CROSSBREEDING_SAPLINGS, max_size + 1):
        if with_repetitions:
            iterator = itertools.combinations_with_replacement(indexes, size)
        else:
            if size > n:
                continue
            iterator = itertools.combinations(indexes, size)
        for combo in iterator:
            if mandatory_count and combo[0] >= mandatory_count:
                # у combinations(_with_replacement) первый индекс — минимальный
                continue
            combos.append(combo)
    return combos


def _remember_map(groups: Dict[str, _MapGroup], item: _GeneticsMap) -> None:
    group = groups.get(item.result)
    if group is None:
        groups[item.result] = _MapGroup(item.result, [item])
        return
    group.maps.append(item)
    group.maps.sort(key=_map_sort_key)
    del group.maps[MAPS_PER_GENE_LIMIT:]


def _simulate_generation(
    source: List[_Sapling],
    *,
    generation_index: int,
    mandatory_count: int,
    gene_scores: Dict[str, float],
    minimum_tracked_score: float,
    groups: Dict[str, _MapGroup],
) -> List[_GeneticsMap]:
    """Один проход simulateCrossbreeding для текущего source."""
    source_genes = [s.genes for s in source]
    source_gene_set = set(source_genes)
    pool_tuple = tuple(dict.fromkeys(source_genes))  # уникальные строки для центров/кэша
    generation_maps: List[_GeneticsMap] = []

    for index_combo in _collect_combos(source, mandatory_count=mandatory_count):
        donors = tuple(source[i].genes for i in index_combo)
        # object-identity: центр — любой sapling, чей объект НЕ в combo
        combo_indexes = set(index_combo)
        # outcomes через кэш по строкам (как crossbreed_combination)
        for result, center, chance, planting_order in _breed_combo_cached(donors, pool_tuple):
            # handlePotentialResultSaplings: не возвращать гены, уже есть в source
            if result in source_gene_set:
                continue

            score = round(sum(gene_scores.get(ch, 0.0) for ch in result), 2)
            if score < minimum_tracked_score:
                continue

            center_index: Optional[int] = None
            if center is not None:
                for i, sapling in enumerate(source):
                    if i in combo_indexes:
                        continue
                    if sapling.genes == center:
                        center_index = i
                        break
                if center_index is None:
                    continue

            composing = sum(source[i].generation_index for i in index_combo)
            if center_index is not None:
                composing += source[center_index].generation_index

            item = _GeneticsMap(
                result=result,
                crossbreeding=donors,
                score=score,
                chance=chance,
                generation_index=generation_index,
                sum_of_composing_generations=composing,
                center=center,
                planting_order=planting_order,
                crossbreeding_indexes=index_combo,
                center_index=center_index,
            )
            generation_maps.append(item)
            _remember_map(groups, item)

    return generation_maps


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
) -> Tuple[Dict[str, _MapGroup], Set[str]]:
    """Полный прогон как CrossbreedingOrchestrator.simulateBestGenetics."""
    originals = _unique_pool(available)
    if not originals:
        return {}, set()

    scores = gene_scores or GENE_SCORES
    generation_limit = max_generations if max_generations is not None else DEFAULT_MAX_STEPS
    source = [_Sapling(gene, 0) for gene in originals]
    groups: Dict[str, _MapGroup] = {}
    original_set = set(originals)

    for generation_index in range(1, generation_limit + 1):
        # added saplings стоят в начале source (как [...additional, ...prev])
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
        # nextGenerationSourceGenes = [...additional, ...source]
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

    # поколения по возрастанию, чтобы родители были готовы
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
            # родитель ещё не в paths_to — попробуем только из originals
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
            break  # один лучший путь на ген
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
    groups, originals = simulate_best_genetics(pool, max_generations=generation_limit)
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
            # ген из исходного пула
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
