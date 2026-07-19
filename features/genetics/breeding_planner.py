from __future__ import annotations

import itertools
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Iterable, List, Optional, Set, Tuple

from features.genetics.calculator import crossbreed_combination, normalize_genes
from features.shared_data import VALID_GENES

MIN_CROSSBREEDING_SAPLINGS = 2
MAX_CROSSBREEDING_SAPLINGS = 5
DEFAULT_MAX_STEPS = 2
EARLY_EXIT_PATHS = 6
EARLY_EXIT_PERFECT_PATHS = 3
SAPLINGS_ADDED_BETWEEN_GENERATIONS = 20
MIN_TRACKED_SCORE = 4.0
GENE_SCORES: Dict[str, float] = {"G": 1.0, "Y": 1.0, "H": 0.5, "W": 0.0, "X": 0.0}


@dataclass(frozen=True)
class BreedStep:
    center: Optional[str]
    crossbreeding: Tuple[str, ...]
    result: str
    chance: float
    # Метки порядка посадки доноров (1, 2, …) или None — как 1st/2nd в гайде rustbreeder.
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


def _profile_distance(genes: str, target_counts: Dict[str, int]) -> int:
    counts = gene_counts(genes)
    return sum(abs(counts[gene] - target_counts[gene]) for gene in VALID_GENES)


def _sapling_score(genes: str) -> float:
    return round(sum(GENE_SCORES.get(gene, 0.0) for gene in normalize_genes(genes)), 2)


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


def _candidate_path(
    step: BreedStep,
    crossbreeding: Tuple[str, ...],
    pool_set: Set[str],
    paths_to: Dict[str, List[BreedStep]],
) -> Optional[List[BreedStep]]:
    parents = set(crossbreeding)
    if step.center:
        parents.add(step.center)

    bred_parents = [gene for gene in parents if gene not in pool_set]
    base_path = _merge_prerequisite_paths(bred_parents, pool_set, paths_to)
    if base_path is None:
        return None

    available = set(pool_set)
    for prior_step in base_path:
        available.add(prior_step.result)
    if not parents.issubset(available):
        return None

    return base_path + [step]


def validate_path(pool: Iterable[str], steps: List[BreedStep]) -> bool:
    pool_set = set(_unique_pool(pool))
    available = set(pool_set)
    for step in steps:
        needed = set(step.crossbreeding)
        if step.center:
            needed.add(step.center)
        if not needed.issubset(available):
            return False
        available.add(step.result)
    return True


def _collect_combos(source: List[str], mandatory_count: int) -> List[Tuple[str, ...]]:
    indexes = list(range(len(source)))
    combos: List[Tuple[str, ...]] = []

    for combo_size in range(MIN_CROSSBREEDING_SAPLINGS, MAX_CROSSBREEDING_SAPLINGS + 1):
        for combo_indexes in itertools.combinations_with_replacement(indexes, combo_size):
            if mandatory_count and combo_indexes[0] >= mandatory_count:
                continue
            combos.append(tuple(source[index] for index in combo_indexes))
    return combos


def _map_sort_key(gene: str, path: List[BreedStep]) -> Tuple[float, float, int, str]:
    return (
        _sapling_score(gene),
        _path_chance(path),
        -len(path),
        gene,
    )


def _pick_saplings_for_next_generation(
    pool: List[str],
    generation_results: Dict[str, List[BreedStep]],
    count: int,
) -> List[str]:
    if not generation_results:
        return []

    maps_to_consider = list(generation_results.items())
    column_scores = [0.0] * 6
    for gene in pool:
        for index, char in enumerate(gene):
            column_scores[index] += GENE_SCORES.get(char, 0.0)

    picked: List[str] = []
    for _ in range(min(count, len(maps_to_consider))):
        columns_worst_to_best = sorted(range(6), key=lambda index: column_scores[index])
        subset = maps_to_consider
        for column in columns_worst_to_best:
            best_col_score = max(GENE_SCORES.get(gene[column], 0.0) for gene, _ in subset)
            subset = [
                (gene, path)
                for gene, path in subset
                if GENE_SCORES.get(gene[column], 0.0) == best_col_score
            ]

        subset.sort(key=lambda item: _map_sort_key(item[0], item[1]), reverse=True)
        best_gene, best_path = subset[0]
        picked.append(best_gene)

        for index, char in enumerate(best_gene):
            column_scores[index] += GENE_SCORES.get(char, 0.0)

        maps_to_consider = [
            (gene, path) for gene, path in maps_to_consider if gene != best_gene
        ]

    return picked


def _should_stop_search(found: List[BreedingPath], max_paths: int) -> bool:
    if len(found) >= max_paths:
        return True
    if len(found) >= EARLY_EXIT_PATHS:
        return True
    perfect = sum(1 for path in found if path.chance >= 0.9999)
    return perfect >= EARLY_EXIT_PERFECT_PATHS


def _simulate_generations(
    pool: List[str],
    target_counts: Dict[str, int],
    *,
    max_generations: int,
    max_paths: int,
) -> List[BreedingPath]:
    pool_set = set(pool)
    found: List[BreedingPath] = []
    paths_to: Dict[str, List[BreedStep]] = {gene: [] for gene in pool}

    source = list(pool)
    mandatory_count = 0

    for _generation in range(1, max_generations + 1):
        generation_results: Dict[str, List[BreedStep]] = {}
        source_tuple = tuple(source)
        combos = _collect_combos(source, mandatory_count)

        for crossbreeding in combos:
            for result, step_center, chance, planting_order in _breed_combo_cached(
                crossbreeding, source_tuple
            ):
                if result in pool_set:
                    continue
                matches_target = matches_gene_counts(result, target_counts)
                if _sapling_score(result) < MIN_TRACKED_SCORE and not matches_target:
                    continue

                step = BreedStep(step_center, crossbreeding, result, chance, planting_order)
                candidate = _candidate_path(step, crossbreeding, pool_set, paths_to)
                if candidate is None:
                    continue
                if not validate_path(pool, candidate):
                    continue

                if matches_gene_counts(result, target_counts):
                    found.append(
                        BreedingPath(
                            candidate,
                            result,
                            _path_chance(candidate),
                        )
                    )
                    if _should_stop_search(found, max_paths):
                        return found

                previous = generation_results.get(result)
                if previous is None or _map_sort_key(result, candidate) > _map_sort_key(
                    result, previous
                ):
                    generation_results[result] = candidate

        for gene, path in generation_results.items():
            existing = paths_to.get(gene)
            if existing is None or len(path) < len(existing) or (
                len(path) == len(existing)
                and _path_chance(path) > _path_chance(existing)
            ):
                paths_to[gene] = path

        if _generation >= max_generations:
            break

        added = _pick_saplings_for_next_generation(
            pool,
            generation_results,
            SAPLINGS_ADDED_BETWEEN_GENERATIONS,
        )
        if not added:
            break

        source = added + pool
        mandatory_count = len(added)

    return found


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
    found = _simulate_generations(
        pool,
        target_counts,
        max_generations=generation_limit,
        max_paths=max_paths,
    )

    if not found:
        return [], (
            f"Пути не найдены за {generation_limit} поколений с {len(pool)} генами. "
            "Попробуйте добавить растения ближе к цели или увеличить глубину поиска."
        )

    found.sort(
        key=lambda item: (
            -round(item.chance, 6),
            item.step_count,
            item.final,
        )
    )
    unique: List[BreedingPath] = []
    seen_finals: Set[str] = set()
    for path in found:
        if path.final in seen_finals:
            continue
        seen_finals.add(path.final)
        unique.append(path)
        if len(unique) >= max_paths:
            break

    return unique, None


def format_gene_profile(counts: Dict[str, int]) -> str:
    parts = [f"{count}{gene}" for gene, count in counts.items() if count > 0]
    return " ".join(parts) if parts else "—"
