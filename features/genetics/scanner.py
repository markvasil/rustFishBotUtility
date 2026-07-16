from __future__ import annotations

import colorsys
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

import mss
import numpy as np
from PIL import Image

from features.genetics.calibration import RegionCalibration
from features.genetics.letter_templates import GENE_LETTER_TEMPLATES
from features.shared_data import VALID_GENES

SlotRect = Tuple[int, int, int, int]

ScanCallback = Callable[[str, str], None]
StatusCallback = Callable[[str], None]

SUPPORTED_ASPECT_RATIO = 16 / 9
SCAN_INTERVAL_SEC = 0.2
MIN_SLOT_SIZE = 12

# Эталонные RGB для плиток генов Rust (обновлены под актуальный UI).
GENE_RGB_REF: Dict[str, Tuple[float, float, float]] = {
    "G": (88.0, 158.0, 62.0),
    "Y": (204.0, 162.0, 48.0),
    "H": (72.0, 118.0, 188.0),
    "W": (168.0, 58.0, 54.0),
    "X": (58.0, 46.0, 46.0),
}


@dataclass(frozen=True)
class ScanRegion:
    id: str
    label: str
    gene_width: float
    gene_height: float
    first_gene_x_center: float
    first_gene_y_center: float
    distance_between_genes: float
    search_x1: float
    search_x2: float
    search_y1: float
    search_y2: float
    gene_x_centers: Tuple[float, ...] = ()


@dataclass(frozen=True)
class ResolutionProfile:
    id: str
    label: str
    ref_width: int
    ref_height: int
    regions: Dict[str, ScanRegion]


def _make_regions() -> Dict[str, ScanRegion]:
    return {
        "planter": ScanRegion(
            id="planter",
            label="Грядка",
            gene_width=0.008,
            gene_height=0.015,
            first_gene_x_center=0.42,
            first_gene_y_center=0.2845,
            distance_between_genes=0.01405,
            search_x1=0.30,
            search_x2=0.68,
            search_y1=0.24,
            search_y2=0.36,
        ),
        "inventory": ScanRegion(
            id="inventory",
            label="Инвентарь",
            gene_width=0.0094,
            gene_height=0.0185,
            first_gene_x_center=0.4195,
            first_gene_y_center=0.2836,
            distance_between_genes=0.0140,
            search_x1=0.395,
            search_x2=0.52,
            search_y1=0.272,
            search_y2=0.298,
            gene_x_centers=(
                0.41953125,
                0.434636,
                0.44765625,
                0.458984375,
                0.476691,
                0.489973,
            ),
        ),
    }


_REGIONS = _make_regions()

RESOLUTION_PROFILES: Dict[str, ResolutionProfile] = {
    "1080p": ResolutionProfile("1080p", "1080p", 1920, 1080, _REGIONS),
    "1440p": ResolutionProfile("1440p", "2K (1440p)", 2560, 1440, _REGIONS),
}

SCAN_REGIONS = _REGIONS

GENE_HSV_PROFILES: Dict[str, Tuple[float, float, float]] = {
    "G": (0.33, 0.55, 0.62),
    "Y": (0.13, 0.78, 0.80),
    "H": (0.58, 0.62, 0.74),
    "W": (0.01, 0.68, 0.66),
    "X": (0.02, 0.18, 0.32),
}

SLOT_WIDTH_SPACING_RATIO = 0.42
SLOT_HEIGHT_RATIO = 0.52
SLOT_HALF_W_MIN = 14
SLOT_HALF_H_MIN = 16
LETTER_PATCH_SIZE = (10, 14)
LETTER_JACCARD_MIN = 0.30
LETTER_JACCARD_GAP = 0.05

_GENE_LETTER_TEMPLATES = GENE_LETTER_TEMPLATES



def resolve_profile(width: int, height: int, profile_id: Optional[str] = None) -> ResolutionProfile:
    if profile_id and profile_id in RESOLUTION_PROFILES:
        return RESOLUTION_PROFILES[profile_id]

    return min(
        RESOLUTION_PROFILES.values(),
        key=lambda profile: abs(profile.ref_width - width) + abs(profile.ref_height - height),
    )


def get_regions_for_frame(width: int, height: int, profile_id: Optional[str] = None) -> Dict[str, ScanRegion]:
    return resolve_profile(width, height, profile_id).regions


def find_rust_hwnd() -> Optional[int]:
    try:
        import win32gui
    except ImportError:
        return None

    matches: List[Tuple[int, str]] = []

    def callback(handle: int, _extra: object) -> bool:
        if not win32gui.IsWindowVisible(handle):
            return True
        title = win32gui.GetWindowText(handle)
        if title == "Rust":
            matches.append((handle, title))
        return True

    try:
        win32gui.EnumWindows(callback, None)
    except Exception:
        return None

    return matches[0][0] if matches else None


def find_rust_window_capture_area() -> Optional[Dict[str, int]]:
    hwnd = find_rust_hwnd()
    if hwnd is None:
        return None

    try:
        import win32gui
    except ImportError:
        return None

    try:
        left, top = win32gui.ClientToScreen(hwnd, (0, 0))
        client = win32gui.GetClientRect(hwnd)
        width = client[2] - client[0]
        height = client[3] - client[1]
        if width < 640 or height < 360:
            return None
        return {"left": left, "top": top, "width": width, "height": height}
    except Exception:
        return None


def normalize_capture_frame(raw: Image.Image) -> Image.Image:
    width, height = raw.size
    aspect = width / height if height else SUPPORTED_ASPECT_RATIO
    if abs(aspect - SUPPORTED_ASPECT_RATIO) < 0.01:
        return raw

    expected_height = round(width / SUPPORTED_ASPECT_RATIO)
    if expected_height <= height:
        y_offset = height - expected_height
        return raw.crop((0, y_offset, width, height))

    expected_width = round(height * SUPPORTED_ASPECT_RATIO)
    x_offset = (width - expected_width) // 2
    return raw.crop((x_offset, 0, x_offset + expected_width, height))


def _prepare_slot(slot_rgb: np.ndarray) -> np.ndarray:
    h, w = slot_rgb.shape[:2]
    if h >= MIN_SLOT_SIZE and w >= MIN_SLOT_SIZE:
        return slot_rgb

    scale = max(MIN_SLOT_SIZE / max(h, 1), MIN_SLOT_SIZE / max(w, 1), 1.0)
    new_w = max(MIN_SLOT_SIZE, int(round(w * scale)))
    new_h = max(MIN_SLOT_SIZE, int(round(h * scale)))
    slot = Image.fromarray(slot_rgb).resize((new_w, new_h), Image.Resampling.NEAREST)
    return np.array(slot)


def _upscale_for_letters(slot_rgb: np.ndarray) -> np.ndarray:
    slot_rgb = _prepare_slot(slot_rgb)
    h, w = slot_rgb.shape[:2]
    target = max(64, min(h, w) * 3)
    scale = max(1.0, target / min(h, w))
    new_w = max(MIN_SLOT_SIZE, int(round(w * scale)))
    new_h = max(MIN_SLOT_SIZE, int(round(h * scale)))
    if new_w == w and new_h == h:
        return slot_rgb
    return np.array(
        Image.fromarray(slot_rgb).resize((new_w, new_h), Image.Resampling.NEAREST)
    )


def _letter_patch_from_mask(mask: np.ndarray) -> Optional[np.ndarray]:
    ys, xs = np.where(mask)
    if len(xs) < 8:
        return None

    fill = len(xs) / mask.size
    if fill < 0.008 or fill > 0.45:
        return None

    x1, x2 = int(xs.min()), int(xs.max())
    y1, y2 = int(ys.min()), int(ys.max())
    if x2 - x1 < 2 or y2 - y1 < 3:
        return None

    patch = mask[y1 : y2 + 1, x1 : x2 + 1].astype(np.uint8)
    resized = Image.fromarray(patch * 255).resize(LETTER_PATCH_SIZE, Image.Resampling.NEAREST)
    return np.array(resized, dtype=np.float32) / 255.0


def _extract_gene_letter_patch(slot_rgb: np.ndarray) -> Optional[np.ndarray]:
    slot_rgb = _prepare_slot(slot_rgb)
    h, w = slot_rgb.shape[:2]
    upscaled = np.array(
        Image.fromarray(slot_rgb).resize((w * 5, h * 5), Image.Resampling.NEAREST)
    )
    gray = upscaled.mean(axis=2)

    best_patch: Optional[np.ndarray] = None
    best_score = 999.0
    for pct in range(76, 98, 2):
        threshold = max(float(np.percentile(gray, pct)), 110.0)
        mask = gray >= threshold
        ys, xs = np.where(mask)
        if len(xs) < 8:
            continue
        fill = len(xs) / mask.size
        if fill < 0.008 or fill > 0.45:
            continue
        score = abs(fill - 0.10)
        if score >= best_score:
            continue
        x1, x2, y1, y2 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
        if x2 - x1 < 2 or y2 - y1 < 3:
            continue
        patch = mask[y1 : y2 + 1, x1 : x2 + 1].astype(np.uint8)
        best_patch = np.array(
            Image.fromarray(patch * 255).resize(LETTER_PATCH_SIZE, Image.Resampling.NEAREST),
            dtype=np.float32,
        ) / 255.0
        best_score = score

    return best_patch


def _jaccard_similarity(a: np.ndarray, b: np.ndarray) -> float:
    intersection = float((a * b).sum())
    union = float(((a + b) > 0).sum())
    return intersection / union if union else 0.0


def _merge_peak_candidates(
    peak_candidates: List[Tuple[int, float]],
    merge_distance: int,
) -> List[Tuple[int, float]]:
    if not peak_candidates:
        return []

    ordered = sorted(peak_candidates, key=lambda item: item[0])
    clusters: List[List[Tuple[int, float]]] = [[ordered[0]]]
    for px, score in ordered[1:]:
        if px - clusters[-1][-1][0] <= merge_distance:
            clusters[-1].append((px, score))
        else:
            clusters.append([(px, score)])

    merged: List[Tuple[int, float]] = []
    for cluster in clusters:
        weight = sum(score for _, score in cluster)
        if weight <= 0:
            continue
        cx = int(round(sum(px * score for px, score in cluster) / weight))
        merged.append((cx, weight))
    return merged


def _pick_six_gene_peaks(
    clusters: List[Tuple[int, float]],
    width: int,
    region: ScanRegion,
) -> Optional[List[int]]:
    if len(clusters) == 6:
        return [px for px, _ in clusters]
    if len(clusters) < 6:
        return None

    if region.gene_x_centers and len(region.gene_x_centers) >= 6:
        refs = [int(round(width * x_center)) for x_center in region.gene_x_centers]
        best_cost = float("inf")
        best_peaks: Optional[List[int]] = None
        for index in range(len(clusters) - 5):
            window = [px for px, _ in clusters[index : index + 6]]
            cost = sum(abs(window[i] - refs[i]) for i in range(6))
            if cost < best_cost:
                best_cost = cost
                best_peaks = window
        return best_peaks

    best_score = float("-inf")
    best_peaks = None
    for index in range(len(clusters) - 5):
        window = clusters[index : index + 6]
        xs = [px for px, _ in window]
        spacings = [xs[i + 1] - xs[i] for i in range(5)]
        spacing_penalty = float(np.std(spacings)) if spacings else 0.0
        score = sum(weight for _, weight in window) - spacing_penalty * 0.75
        if score > best_score:
            best_score = score
            best_peaks = xs
    return best_peaks


def _select_peaks_by_score(
    peak_candidates: List[Tuple[int, float]],
    min_distance: int,
) -> List[int]:
    selected: List[int] = []
    for peak_x, _score in sorted(peak_candidates, key=lambda item: -item[1]):
        if all(abs(peak_x - chosen) >= min_distance for chosen in selected):
            selected.append(peak_x)
    selected.sort()
    return selected


def _resolve_letter_tie(first: str, second: str, patch: np.ndarray) -> str:
    height, width = patch.shape
    left = float(patch[:, : width // 3].sum())
    right = float(patch[:, (2 * width) // 3 :].sum())
    mid = float(patch[:, width // 3 : (2 * width) // 3].sum())
    top = float(patch[: height // 2, :].sum())
    bottom = float(patch[height // 2 :, :].sum())
    mid_row = float(patch[max(0, height // 2 - 1) : min(height, height // 2 + 2), :].sum())
    stem = float(patch[height // 2 :, width // 3 : (2 * width) // 3].sum())
    pair = {first, second}

    if pair == {"W", "Y"}:
        bottom_band = patch[(2 * height) // 3 :, :]
        wide = float(bottom_band[:, : width // 3].sum()) + float(bottom_band[:, (2 * width) // 3 :].sum())
        return "W" if wide > float(bottom_band[:, width // 3 : (2 * width) // 3].sum()) else "Y"
    if pair == {"W", "H"}:
        return "H" if mid_row > (left + right) * 0.42 else "W"
    if pair == {"W", "G"}:
        bottom = patch[(2 * height) // 3 :, :]
        bottom_outer = float(bottom[:, : width // 3].sum()) + float(bottom[:, (2 * width) // 3 :].sum())
        bottom_inner = float(bottom[:, width // 3 : (2 * width) // 3].sum())
        if bottom_outer > max(bottom_inner * 0.85, 1.0):
            return "W"
        mid_right = float(patch[height // 3 : (2 * height) // 3, (2 * width) // 3 :].sum())
        return "G" if mid_right > 1.2 else "W"
    if pair == {"G", "H"}:
        return "H" if (left + right) > float(patch.sum()) * 0.55 else "G"
    if pair == {"G", "Y"}:
        return "G" if float(patch.sum()) > 5.0 else "Y"
    if pair == {"W", "X"}:
        diag1 = sum(patch[i, i] for i in range(min(height, width)))
        diag2 = sum(patch[i, width - 1 - i] for i in range(min(height, width)))
        return "X" if min(diag1, diag2) >= 1.5 else "W"
    if "W" in pair and mid_row <= (left + right) * 0.38 and bottom > top * 0.7:
        return "W"
    if "Y" in pair and top > bottom and stem > mid * 0.45:
        return "Y"
    return first


def _match_gene_letter_templates(patch: np.ndarray) -> Tuple[Optional[str], float]:
    scores: List[Tuple[str, float]] = []
    for gene, templates in _GENE_LETTER_TEMPLATES.items():
        best = max(_jaccard_similarity(patch, template) for template in templates)
        scores.append((gene, best))

    scores.sort(key=lambda item: item[1], reverse=True)
    if not scores:
        return None, 0.0

    best_gene, best_score = scores[0]
    second_gene = scores[1][0] if len(scores) > 1 else ""
    second_score = scores[1][1] if len(scores) > 1 else 0.0

    if best_score < LETTER_JACCARD_MIN:
        if best_score >= 0.24 and second_score >= 0.24 and best_score - second_score < LETTER_JACCARD_GAP * 2:
            return _resolve_letter_tie(best_gene, second_gene, patch), best_score
        return None, best_score

    if best_score - second_score < LETTER_JACCARD_GAP:
        return _resolve_letter_tie(best_gene, second_gene, patch), best_score
    if {best_gene, second_gene} == {"W", "Y"} and best_score - second_score < 0.10:
        return _resolve_letter_tie(best_gene, second_gene, patch), best_score
    if {best_gene, second_gene} == {"W", "H"} and best_score - second_score < 0.12:
        return _resolve_letter_tie(best_gene, second_gene, patch), best_score
    return best_gene, best_score


def _classify_by_letter(slot_rgb: np.ndarray) -> Tuple[Optional[str], float]:
    patch = _extract_gene_letter_patch(slot_rgb)
    if patch is None:
        return None, 0.0
    return _match_gene_letter_templates(patch)


def _find_feature_center(slot_rgb: np.ndarray) -> Tuple[int, int]:
    slot_rgb = _upscale_for_letters(slot_rgb)
    h, w = slot_rgb.shape[:2]
    gray = slot_rgb.mean(axis=2)

    letter_mask = gray >= max(float(np.median(gray)) + 28.0, 110.0)
    ys, xs = np.where(letter_mask)
    if len(xs) >= 16:
        return int(xs.mean()), int(ys.mean())

    best_score = -1.0
    best_x, best_y = w // 2, h // 2
    for y in range(h):
        for x in range(w):
            pixel = slot_rgb[y, x].astype(np.float32)
            sat, val = _pixel_saturation_value(float(pixel[0]), float(pixel[1]), float(pixel[2]))
            score = sat * val
            if score > best_score:
                best_score = score
                best_x, best_y = x, y
    return best_x, best_y


def _classify_by_accent(slot_rgb: np.ndarray) -> Tuple[Optional[str], float]:
    """Только тёмный X без читаемой буквы. W/X с красным кругом различаются по букве."""
    slot_rgb = _upscale_for_letters(slot_rgb)
    pixels = slot_rgb.reshape(-1, 3).astype(np.float32)
    dark_red: List[float] = []

    for pixel in pixels:
        if float(pixel.mean()) > 195.0:
            continue
        avg_r, avg_g, avg_b = float(pixel[0]), float(pixel[1]), float(pixel[2])
        sat, val = _pixel_saturation_value(avg_r, avg_g, avg_b)
        if sat < 0.18 or val >= 0.40:
            continue
        hue = colorsys.rgb_to_hsv(avg_r / 255.0, avg_g / 255.0, avg_b / 255.0)[0]
        if hue <= 0.08 or hue >= 0.92:
            dark_red.append(sat * val)

    if len(dark_red) < 24:
        return None, 0.0

    confidence = min(1.0, sum(dark_red[:32]) / 8.0)
    if confidence >= ACCENT_MIN_CONFIDENCE:
        return "X", confidence
    return None, 0.0


def _hsv_distance(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    dh = min(abs(a[0] - b[0]), 1 - abs(a[0] - b[0]))
    ds = abs(a[1] - b[1])
    dv = abs(a[2] - b[2])
    return dh * 2.0 + ds * 1.2 + dv * 1.0


def _pixel_saturation_value(r: float, g: float, b: float) -> Tuple[float, float]:
    rgb = np.array([r, g, b], dtype=np.float32) / 255.0
    maxc = float(rgb.max())
    minc = float(rgb.min())
    sat = (maxc - minc) / maxc if maxc > 0 else 0.0
    return sat, maxc


def _nearest_gene_rgb(pixel: np.ndarray) -> Tuple[Optional[str], float]:
    best_gene: Optional[str] = None
    best_dist = float("inf")
    for gene, ref in GENE_RGB_REF.items():
        dist = float(np.linalg.norm(pixel - np.array(ref)))
        if dist < best_dist:
            best_dist = dist
            best_gene = gene
    return best_gene, best_dist


def classify_gene_slot(slot_rgb: np.ndarray) -> Optional[str]:
    if slot_rgb.size == 0:
        return None

    letter, _confidence = _classify_by_letter(slot_rgb)
    return letter


def _classify_strip(strip: np.ndarray) -> Tuple[Optional[str], int]:
    if strip.size == 0:
        return None, 0

    _, pw = strip.shape[:2]
    if pw < 48:
        return None, 0

    slot_w = max(1, pw // 6)
    genes: List[Optional[str]] = []
    for index in range(6):
        x1 = index * slot_w
        x2 = (index + 1) * slot_w if index < 5 else pw
        gene = classify_gene_slot(strip[:, x1:x2])
        genes.append(gene)

    score = sum(1 for gene in genes if gene)
    if score < 6:
        return None, score

    return "".join(gene for gene in genes if gene), score


def _search_region_adaptive(
    frame: Image.Image,
    region: ScanRegion,
    offset: Tuple[int, int] = (0, 0),
) -> Optional[str]:
    arr = np.array(frame.convert("RGB"))
    height, width = arr.shape[:2]
    dx, dy = offset
    x1 = int(width * region.search_x1) + dx
    x2 = int(width * region.search_x2) + dx
    if x2 - x1 < 80:
        return None

    best_genes: Optional[str] = None
    best_score = 0

    for y_frac in np.linspace(region.search_y1, region.search_y2, 40):
        y = int(height * y_frac) + dy
        strip_h = max(14, int(height * 0.024))
        if y + strip_h >= height or y < 0:
            continue
        x1c = max(0, x1)
        x2c = min(width, x2)
        if x2c - x1c < 48:
            continue
        strip = arr[y : y + strip_h, x1c:x2c]
        genes, score = _classify_strip(strip)
        if score > best_score:
            best_score = score
            best_genes = genes

    return best_genes if best_score == 6 else None


def _crop_gene_slots(
    frame: Image.Image,
    region: ScanRegion,
    offset: Tuple[int, int] = (0, 0),
) -> List[np.ndarray]:
    width, height = frame.size
    dx, dy = offset
    slots: List[np.ndarray] = []

    for index in range(6):
        x_center = region.first_gene_x_center + region.distance_between_genes * index
        x_start = int(round(width * (x_center - region.gene_width / 2))) + dx
        x_end = int(round(width * (x_center + region.gene_width / 2))) + dx
        y_start = int(round(height * (region.first_gene_y_center - region.gene_height / 2))) + dy
        y_end = int(round(height * (region.first_gene_y_center + region.gene_height / 2))) + dy

        x_start = max(0, min(x_start, width - 1))
        x_end = max(x_start + 1, min(x_end, width))
        y_start = max(0, min(y_start, height - 1))
        y_end = max(y_start + 1, min(y_end, height))

        slot = frame.crop((x_start, y_start, x_end, y_end))
        slots.append(np.array(slot.convert("RGB")))

    return slots


def _detect_gene_row_center_candidates(
    frame: Image.Image,
    region: ScanRegion,
) -> List[List[Tuple[int, int]]]:
    arr = np.array(frame.convert("RGB"))
    height, width = arr.shape[:2]
    y1 = max(0, int(height * region.search_y1))
    y2 = min(height, int(height * region.search_y2))
    x1 = max(0, int(width * region.search_x1))
    x2 = min(width, int(width * region.search_x2))
    if y2 - y1 < 8 or x2 - x1 < 80:
        return []

    red = arr[:, :, 0].astype(int)
    green = arr[:, :, 1].astype(int)
    blue = arr[:, :, 2].astype(int)
    circle_mask = (
        (green > 100) & (green > red + 25) & (green > blue + 15)
        | (red > 100) & (red > green + 35) & (red > blue + 35)
    )
    sub = circle_mask[y1:y2, x1:x2]
    column_hits = sub.sum(axis=0).astype(float)
    peak_threshold = 7.0
    if column_hits.max() < peak_threshold:
        return []

    kernel = np.array([1, 2, 3, 2, 1], dtype=float)
    kernel /= kernel.sum()
    smoothed = np.convolve(column_hits, kernel, mode="same")
    min_distance = max(18, int(round(width * 0.008)))
    merge_distance = max(12, int(round(width * 0.005)))
    peak_candidates: List[Tuple[int, float]] = []
    for index in range(2, len(smoothed) - 2):
        value = smoothed[index]
        if value < peak_threshold:
            continue
        if value >= smoothed[index - 1] and value >= smoothed[index + 1]:
            if value >= smoothed[index - 2] and value >= smoothed[index + 2]:
                peak_candidates.append((x1 + index, value))

    row_hits = sub.sum(axis=1).astype(float)
    row_y = y1 + int(np.argmax(row_hits))
    candidates: List[List[Tuple[int, int]]] = []

    selected = _select_peaks_by_score(peak_candidates, min_distance)
    if len(selected) >= 6:
        candidates.append([(peak_x, row_y) for peak_x in selected[:6]])

    clusters = _merge_peak_candidates(peak_candidates, merge_distance)
    if len(clusters) >= 6:
        picked = _pick_six_gene_peaks(clusters, width, region)
        if picked:
            centers = [(peak_x, row_y) for peak_x in picked]
            if centers not in candidates:
                candidates.append(centers)

    if len(selected) < 6 and len(clusters) >= 6:
        picked = _pick_six_gene_peaks(clusters, width, region)
        if picked:
            centers = [(peak_x, row_y) for peak_x in picked]
            if centers not in candidates:
                candidates.append(centers)

    return candidates


def _detect_gene_row_centers(frame: Image.Image, region: ScanRegion) -> Optional[List[Tuple[int, int]]]:
    candidates = _detect_gene_row_center_candidates(frame, region)
    if not candidates:
        return None
    if len(candidates) == 1 or not region.gene_x_centers:
        return candidates[0]

    width = frame.size[0]
    refs = [int(round(width * x_center)) for x_center in region.gene_x_centers[:6]]

    def alignment_cost(centers: List[Tuple[int, int]]) -> float:
        return float(sum(abs(centers[index][0] - refs[index]) for index in range(6)))

    return min(candidates, key=alignment_cost)


def _has_user_calibration(cal: RegionCalibration) -> bool:
    if cal.dx != 0 or cal.dy != 0:
        return True
    return any(slot != (0, 0) for slot in cal.slots)


def _slot_crop_sizes(width: int, height: int, region: ScanRegion) -> Tuple[int, int]:
    half_w = max(SLOT_HALF_W_MIN, int(round(width * region.gene_width / 2)))
    half_h = max(SLOT_HALF_H_MIN, int(round(height * region.gene_height * SLOT_HEIGHT_RATIO)))
    return half_w, half_h


def _slot_rects_from_centers(
    centers: List[Tuple[int, int]],
    half_w: int,
    half_h: int,
) -> List[SlotRect]:
    return [
        (cx - half_w, cy - half_h, cx + half_w, cy + half_h)
        for cx, cy in centers
    ]


def _slot_centers(
    width: int,
    height: int,
    region: ScanRegion,
    cal: RegionCalibration,
) -> List[Tuple[int, int]]:
    centers: List[Tuple[int, int]] = []
    for index in range(6):
        if region.gene_x_centers and index < len(region.gene_x_centers):
            x_center = region.gene_x_centers[index]
        else:
            x_center = region.first_gene_x_center + region.distance_between_genes * index
        slot_dx, slot_dy = cal.slots[index]
        cx = int(round(width * x_center)) + cal.dx + slot_dx
        cy = int(round(height * region.first_gene_y_center)) + cal.dy + slot_dy
        centers.append((cx, cy))
    return centers


def _slot_half_sizes(
    width: int,
    height: int,
    region: ScanRegion,
    centers: List[Tuple[int, int]],
) -> Tuple[int, int]:
    spacings = [
        centers[index + 1][0] - centers[index][0]
        for index in range(5)
        if centers[index + 1][0] > centers[index][0]
    ]
    if spacings:
        spacing = sum(spacings) / len(spacings)
        half_w = max(SLOT_HALF_W_MIN, int(round(spacing * SLOT_WIDTH_SPACING_RATIO)))
    else:
        half_w = max(SLOT_HALF_W_MIN, int(round(width * region.gene_width / 2)))

    half_h = max(SLOT_HALF_H_MIN, int(round(height * region.gene_height * SLOT_HEIGHT_RATIO)))
    return half_w, half_h


def calibrated_slot_rects(
    width: int,
    height: int,
    region: ScanRegion,
    cal: RegionCalibration,
) -> List[SlotRect]:
    centers = _slot_centers(width, height, region, cal)
    half_w, half_h = _slot_half_sizes(width, height, region, centers)
    rects: List[SlotRect] = []
    for cx, cy in centers:
        rects.append((cx - half_w, cy - half_h, cx + half_w, cy + half_h))
    return rects


def search_rect_from_slots(slot_rects: List[SlotRect], padding: int = 12) -> SlotRect:
    x1 = min(rect[0] for rect in slot_rects) - padding
    y1 = min(rect[1] for rect in slot_rects) - padding
    x2 = max(rect[2] for rect in slot_rects) + padding
    y2 = max(rect[3] for rect in slot_rects) + padding
    return x1, y1, x2, y2


def _expand_rect(rect: SlotRect, scale: float, width: int, height: int) -> SlotRect:
    x1, y1, x2, y2 = rect
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    half_w = (x2 - x1) * scale / 2
    half_h = (y2 - y1) * scale / 2
    nx1 = max(0, int(round(cx - half_w)))
    ny1 = max(0, int(round(cy - half_h)))
    nx2 = min(width, int(round(cx + half_w)))
    ny2 = min(height, int(round(cy + half_h)))
    return nx1, ny1, max(nx1 + 1, nx2), max(ny1 + 1, ny2)


def _classify_slot_from_frame_confidence(
    frame: Image.Image,
    rect: SlotRect,
) -> Tuple[Optional[str], float]:
    width, height = frame.size
    x1, y1, x2, y2 = rect
    x1 = max(0, min(x1, width - 1))
    x2 = max(x1 + 1, min(x2, width))
    y1 = max(0, min(y1, height - 1))
    y2 = max(y1 + 1, min(y2, height))
    base_rect = (x1, y1, x2, y2)

    best_gene: Optional[str] = None
    best_score = 0.0
    for scale in (1.0, 1.35, 1.7):
        crop_rect = base_rect if scale == 1.0 else _expand_rect(base_rect, scale, width, height)
        slot = np.array(frame.crop(crop_rect).convert("RGB"))
        patch = _extract_gene_letter_patch(slot)
        if patch is None:
            continue
        gene, score = _match_gene_letter_templates(patch)
        if gene is not None and score > best_score:
            best_gene, best_score = gene, score

    return best_gene, best_score


def _classify_slot_from_frame(frame: Image.Image, rect: SlotRect) -> Optional[str]:
    gene, _score = _classify_slot_from_frame_confidence(frame, rect)
    return gene


def _genes_from_slot_rects_scored(
    frame: Image.Image,
    rects: List[SlotRect],
) -> Tuple[Optional[str], float]:
    genes: List[str] = []
    scores: List[float] = []
    for rect in rects:
        gene, score = _classify_slot_from_frame_confidence(frame, rect)
        if gene is None:
            return None, 0.0
        genes.append(gene)
        scores.append(score)

    result = "".join(genes)
    if len(result) == 6 and all(ch in VALID_GENES for ch in result):
        return result, sum(scores) / len(scores)
    return None, 0.0


def _genes_from_slot_rects(frame: Image.Image, rects: List[SlotRect]) -> Optional[str]:
    result, _score = _genes_from_slot_rects_scored(frame, rects)
    return result


def _centers_alignment_penalty(
    centers: List[Tuple[int, int]],
    width: int,
    region: ScanRegion,
) -> float:
    if not region.gene_x_centers:
        return 0.0
    refs = [int(round(width * x_center)) for x_center in region.gene_x_centers[:6]]
    return float(sum(abs(centers[index][0] - refs[index]) for index in range(6))) / 6.0


def _crop_slot_rects(frame: Image.Image, slot_rects: List[SlotRect]) -> List[np.ndarray]:
    width, height = frame.size
    slots: List[np.ndarray] = []

    for x_start, y_start, x_end, y_end in slot_rects:
        x_start = max(0, min(x_start, width - 1))
        x_end = max(x_start + 1, min(x_end, width))
        y_start = max(0, min(y_start, height - 1))
        y_end = max(y_start + 1, min(y_end, height))
        slot = frame.crop((x_start, y_start, x_end, y_end))
        slots.append(np.array(slot.convert("RGB")))

    return slots


def _scan_calibrated_slots(
    frame: Image.Image,
    region: ScanRegion,
    calibration: RegionCalibration,
) -> Optional[str]:
    width, height = frame.size
    half_w, half_h = _slot_crop_sizes(width, height, region)

    center_sets: List[List[Tuple[int, int]]] = []
    seen: set[Tuple[Tuple[int, int], ...]] = set()

    def add_centers(centers: List[Tuple[int, int]]) -> None:
        key = tuple(centers)
        if key not in seen:
            seen.add(key)
            center_sets.append(centers)

    for detected in _detect_gene_row_center_candidates(frame, region):
        add_centers(detected)

    add_centers(_slot_centers(width, height, region, RegionCalibration()))
    if _has_user_calibration(calibration):
        add_centers(_slot_centers(width, height, region, calibration))

    best_result: Optional[str] = None
    best_score = -1.0
    for centers in center_sets:
        rects = _slot_rects_from_centers(centers, half_w, half_h)
        result, confidence = _genes_from_slot_rects_scored(frame, rects)
        if not result:
            continue
        score = confidence - _centers_alignment_penalty(centers, width, region) * 0.004
        if score > best_score:
            best_score = score
            best_result = result

    return best_result


def scan_frame_for_genes(
    frame: Image.Image,
    region: ScanRegion,
    *,
    profile_id: Optional[str] = None,
    calibration: Optional[RegionCalibration] = None,
) -> Optional[str]:
    width, height = frame.size
    regions = get_regions_for_frame(width, height, profile_id)
    active = regions.get(region.id, region)
    cal = calibration if calibration is not None else RegionCalibration()
    return _scan_calibrated_slots(frame, active, cal)


class GeneScanner:
    """Фоновый сканер экрана: захватывает кадры и распознаёт гены растений."""

    def __init__(
        self,
        on_gene_found: ScanCallback,
        on_status: Optional[StatusCallback] = None,
        get_calibrations: Optional[Callable[[], Dict[str, RegionCalibration]]] = None,
    ) -> None:
        self._on_gene_found = on_gene_found
        self._on_status = on_status or (lambda _msg: None)
        self._get_calibrations = get_calibrations or (lambda: {})
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._active_regions: List[str] = []
        self._last_seen: Dict[str, str] = {}
        self._profile_id: Optional[str] = None
        self._miss_count = 0

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def set_profile(self, profile_id: Optional[str]) -> None:
        mapping = {"Авто": None, "1080p": "1080p", "2K": "1440p"}
        self._profile_id = mapping.get(profile_id or "", profile_id)

    def start(self, region_ids: Optional[List[str]] = None, profile_id: Optional[str] = None) -> None:
        if profile_id is not None:
            self.set_profile(profile_id)

        if self.is_running:
            return

        self._active_regions = [
            rid for rid in (region_ids or list(_REGIONS))
            if rid in _REGIONS
        ]
        if not self._active_regions:
            self._active_regions = list(_REGIONS)

        self._last_seen.clear()
        self._miss_count = 0
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="GeneScanner")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def stop_async(self, on_stopped: Optional[Callable[[], None]] = None) -> None:
        self._stop_event.set()
        self._on_status("Останавливаем сканирование…")
        thread = self._thread
        if not thread or not thread.is_alive():
            self._thread = None
            self._on_status("Сканирование остановлено")
            if on_stopped:
                on_stopped()
            return

        def waiter() -> None:
            thread.join(timeout=2.0)
            self._thread = None
            self._on_status("Сканирование остановлено")
            if on_stopped:
                on_stopped()

        threading.Thread(target=waiter, daemon=True, name="GeneScannerStop").start()

    def _run_loop(self) -> None:
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                reported = False
                rust_hwnd = find_rust_hwnd()

                while not self._stop_event.is_set():
                    capture = find_rust_window_capture_area()
                    source = "окно Rust"
                    from_window = capture is not None

                    if capture:
                        shot = sct.grab(capture)
                    else:
                        shot = sct.grab(monitor)
                        source = "монитор"

                    frame = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                    if not from_window:
                        frame = normalize_capture_frame(frame)

                    width, height = frame.size
                    profile = resolve_profile(width, height, self._profile_id)
                    regions = get_regions_for_frame(width, height, profile.id)

                    if not reported:
                        reported = True
                        if rust_hwnd is None:
                            self._on_status("Rust не найден — запустите игру")
                        else:
                            self._on_status(
                                f"Сканирование: {width}×{height}, {profile.label}, {source}. "
                                "Откройте растение в Rust"
                            )

                    found_any = False
                    calibrations = self._get_calibrations()
                    for region_id in self._active_regions:
                        region = regions.get(region_id)
                        if region is None:
                            continue
                        calibration = calibrations.get(region_id, RegionCalibration())
                        genes = scan_frame_for_genes(
                            frame,
                            region,
                            profile_id=profile.id,
                            calibration=calibration,
                        )
                        if genes and self._last_seen.get(region_id) != genes:
                            self._last_seen[region_id] = genes
                            self._on_gene_found(genes, region_id)
                            found_any = True
                            self._miss_count = 0

                    if not found_any:
                        self._miss_count += 1
                        if self._miss_count == 15:
                            self._on_status(
                                f"Гены не видны ({width}×{height}). "
                                "Откройте растение в инвентаре или на грядке"
                            )
                            self._miss_count = 0

                    time.sleep(SCAN_INTERVAL_SEC)
        except Exception as exc:
            self._on_status(f"Ошибка сканера: {exc}")
