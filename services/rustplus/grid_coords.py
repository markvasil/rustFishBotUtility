"""Мировые координаты Rust+ → игровой грид (Q17, AA3, …).

G-карта в игре: клетки 150 м. Вертикальные границы сдвинуты на
полклетки (75 м) относительно world x=0 — иначе на линии Q/R
маркер визуально оказывается в середине R.
"""

from __future__ import annotations

import string
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

# Размер клетки на G-карте (Devblog 181).
GRID_DIAMETER = 150.0
# Сдвиг сетки по X (и по Y от севера), чтобы совпасть с линиями в игре.
GRID_ORIGIN = GRID_DIAMETER / 2.0  # 75


def _letter_codes() -> List[str]:
    letters = list(string.ascii_uppercase)
    letters.extend(a + b for a in string.ascii_uppercase for b in string.ascii_uppercase)
    return letters


_LETTERS = _letter_codes()


def number_to_letters(index: int) -> str:
    """0-based индекс колонки → A…Z, AA…"""
    if index < 0:
        return "?"
    if index < len(_LETTERS):
        return _LETTERS[index]
    n = index
    out = ""
    while n >= 0:
        out = chr(ord("A") + (n % 26)) + out
        n = n // 26 - 1
    return out


def world_to_grid(x: float, y: float, map_size: int) -> str:
    """Мировые координаты Rust+ (0..map_size) → ``Q17`` и т.п."""
    if not map_size:
        return "?"
    try:
        fx = float(x)
        fy = float(y)
        size = float(map_size)
    except (TypeError, ValueError):
        return "?"

    col = int((fx - GRID_ORIGIN) // GRID_DIAMETER)
    row = int((size - fy - GRID_ORIGIN) // GRID_DIAMETER)
    # Край карты до первой линии сетки (0…75) относится к A0 / нулевой строке.
    col = max(0, col)
    row = max(0, row)
    return f"{number_to_letters(col)}{row}"


def world_to_grid_parts(
    x: float, y: float, map_size: int,
) -> Tuple[Optional[str], Optional[int]]:
    label = world_to_grid(x, y, map_size)
    if label == "?" or not label:
        return None, None
    i = 0
    while i < len(label) and label[i].isalpha():
        i += 1
    letters = label[:i] or None
    try:
        row = int(label[i:]) if i < len(label) else None
    except ValueError:
        row = None
    return letters, row


def generate_grid_overlay(
    map_size: int,
    *,
    text_size: int = 18,
    text_padding: int = 4,
    color: Tuple[int, int, int, int] = (0, 0, 0, 220),
) -> Image.Image:
    """Оверлей сетки с тем же origin/шагом, что world_to_grid."""
    size = int(map_size)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    if size <= 0:
        return img

    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    try:
        from importlib import resources

        with resources.path("rustplus.utils.fonts", "PermanentMarker.ttf") as path:
            font = ImageFont.truetype(str(path), text_size)
    except Exception:
        try:
            font = ImageFont.truetype("arial.ttf", text_size)
        except OSError:
            pass

    # Колонка i: world x ∈ [ORIGIN + i*G, ORIGIN + (i+1)*G)
    # Строка j сверху (север, row=j): отступ ORIGIN от верха изображения.
    num_cols = int((size - GRID_ORIGIN) / GRID_DIAMETER) + 1
    num_rows = int((size - GRID_ORIGIN) / GRID_DIAMETER) + 1
    for i in range(num_cols):
        for j in range(num_rows):
            x0 = int(GRID_ORIGIN + i * GRID_DIAMETER)
            y0 = int(GRID_ORIGIN + j * GRID_DIAMETER)
            x1 = int(GRID_ORIGIN + (i + 1) * GRID_DIAMETER)
            y1 = int(GRID_ORIGIN + (j + 1) * GRID_DIAMETER)
            if x0 >= size or y0 >= size:
                continue
            x1 = min(x1, size - 1)
            y1 = min(y1, size - 1)
            draw.rectangle((x0, y0, x1, y1), outline=color)
            label = f"{number_to_letters(i)}{j}"
            draw.text((x0 + text_padding, y0 + text_padding), label, fill=color, font=font)

    return img
