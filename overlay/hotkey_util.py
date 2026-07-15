"""Точные hotkey-строки: sc:<scan_code> (Num 1 ≠ ряд '1')."""

from __future__ import annotations

from typing import Any, Callable, List, Sequence, Tuple

import keyboard

# Физические scan-code нумпада (Windows).
_NUMPAD_LABELS = {
    71: "Num 7",
    72: "Num 8",
    73: "Num 9",
    75: "Num 4",
    76: "Num 5",
    77: "Num 6",
    79: "Num 1",
    80: "Num 2",
    81: "Num 3",
    82: "Num 0",
    83: "Num .",
    55: "Num *",
    74: "Num -",
    78: "Num +",
    53: "Num /",
    28: "Num Enter",
    69: "Num Lock",
}

_NUMPAD_SCANS = set(_NUMPAD_LABELS)

# Верхний ряд цифр (не нумпад). Legacy-хоткеи "1".."0" сводим сюда.
_DIGIT_TOP_SCAN = {
    "1": 2,
    "2": 3,
    "3": 4,
    "4": 5,
    "5": 6,
    "6": 7,
    "7": 8,
    "8": 9,
    "9": 10,
    "0": 11,
}

_TOP_SCAN_TO_DIGIT = {v: k for k, v in _DIGIT_TOP_SCAN.items()}


def event_to_hotkey(event: Any, modifier_names: Sequence[str] = ()) -> str:
    """Основная клавиша всегда sc:<code>, чтобы Num1 ≠ ряд '1'."""
    scan = int(getattr(event, "scan_code", 0) or 0)
    if scan <= 0:
        name = str(getattr(event, "name", "") or "").lower().strip()
        if not name:
            raise ValueError("empty key event")
        # если библиотека отдала имя цифры без scan — хотя бы не цепляем нумпад
        if name in _DIGIT_TOP_SCAN:
            parts = [m for m in modifier_names if m] + [f"sc:{_DIGIT_TOP_SCAN[name]}"]
            return "+".join(parts)
        parts = [m for m in modifier_names if m] + [name]
        return "+".join(parts)

    parts = [m for m in modifier_names if m]
    parts.append(f"sc:{scan}")
    return "+".join(parts)


def normalize_stored_hotkey(stored: str) -> str:
    """Legacy '1' → sc:2 (верхний ряд). Numpad sc:79 не трогаем."""
    stored = (stored or "").strip().lower()
    if not stored:
        return stored
    if stored in _DIGIT_TOP_SCAN:
        return f"sc:{_DIGIT_TOP_SCAN[stored]}"
    parts: List[str] = []
    for part in stored.split("+"):
        part = part.strip()
        if not part:
            continue
        if part in _DIGIT_TOP_SCAN:
            parts.append(f"sc:{_DIGIT_TOP_SCAN[part]}")
        else:
            parts.append(part)
    return "+".join(parts)


def hotkey_label(stored: str) -> str:
    """Человекочитаемая подпись для UI."""
    stored = normalize_stored_hotkey(stored)
    if not stored:
        return "?"
    out: List[str] = []
    for part in stored.split("+"):
        part = part.strip()
        if part.startswith("sc:"):
            try:
                scan = int(part[3:])
            except ValueError:
                out.append(part)
                continue
            out.append(_scan_to_name(scan))
        else:
            out.append(part.upper() if len(part) <= 3 else part)
    return "+".join(out)


def _scan_to_name(scan: int) -> str:
    if scan in _NUMPAD_LABELS:
        return _NUMPAD_LABELS[scan]
    if scan in _TOP_SCAN_TO_DIGIT:
        return _TOP_SCAN_TO_DIGIT[scan]
    try:
        for name_candidate in (
            "f1", "f2", "f3", "f4", "f5", "f6",
            "f7", "f8", "f9", "f10", "f11", "f12",
        ):
            codes = keyboard.key_to_scan_codes(name_candidate, False)
            if scan in codes:
                return name_candidate.upper()
    except Exception:
        pass
    return f"Key#{scan}"


def parse_hotkey_parts(stored: str) -> List[Any]:
    """Части для keyboard.add_hotkey: только точные scan-codes / имена без двусмысленности."""
    stored = normalize_stored_hotkey(stored)
    parts: List[Any] = []
    for part in stored.split("+"):
        part = part.strip()
        if not part:
            continue
        if part.startswith("sc:"):
            parts.append(int(part[3:]))
        else:
            parts.append(part)
    return parts


def add_hotkey_precise(stored: str, callback: Callable[[], None], *, suppress: bool = False) -> Any:
    parts = parse_hotkey_parts(stored)
    if not parts:
        raise ValueError("empty hotkey")
    if len(parts) == 1:
        return keyboard.add_hotkey(parts[0], callback, suppress=suppress)
    return keyboard.add_hotkey(parts, callback, suppress=suppress)


def is_numpad_hotkey(stored: str) -> bool:
    stored = normalize_stored_hotkey(stored)
    for part in stored.split("+"):
        part = part.strip()
        if part.startswith("sc:"):
            try:
                if int(part[3:]) in _NUMPAD_SCANS:
                    return True
            except ValueError:
                continue
    return False


def current_modifiers() -> Tuple[str, ...]:
    mods: List[str] = []
    try:
        if keyboard.is_pressed("ctrl"):
            mods.append("ctrl")
        if keyboard.is_pressed("alt"):
            mods.append("alt")
        if keyboard.is_pressed("shift"):
            mods.append("shift")
    except Exception:
        pass
    return tuple(mods)
