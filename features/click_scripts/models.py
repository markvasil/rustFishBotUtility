from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List
from uuid import uuid4


MOUSE_BUTTONS = ("left", "right", "middle")
MOUSE_BUTTON_LABELS = {
    "left": "ЛКМ",
    "right": "ПКМ",
    "middle": "СКМ",
}

# key -> label for UI; "" means no hold
HOLD_KEYS: tuple[tuple[str, str], ...] = (
    ("", "Нет"),
    ("shift", "Shift"),
    ("ctrl", "Ctrl"),
    ("alt", "Alt"),
    ("w", "W"),
    ("a", "A"),
    ("s", "S"),
    ("d", "D"),
    ("space", "Пробел"),
    ("e", "E"),
    ("r", "R"),
    ("f", "F"),
    ("c", "C"),
    ("v", "V"),
    ("q", "Q"),
    ("tab", "Tab"),
    ("caps lock", "Caps Lock"),
)

HOLD_KEY_LABELS = {key: label for key, label in HOLD_KEYS}
HOLD_KEY_VALUES = {label: key for key, label in HOLD_KEYS}
ALLOWED_HOLD_KEYS = {key for key, _ in HOLD_KEYS}


@dataclass
class ScriptStep:
    kind: str = "click"  # click | delay
    x: int = 0
    y: int = 0
    mouse_button: str = "left"
    interval_ms: int = 200
    click_count: int = 1
    hold_key: str = ""
    delay_ms: int = 1000

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "x": self.x,
            "y": self.y,
            "mouse_button": self.mouse_button,
            "interval_ms": self.interval_ms,
            "click_count": self.click_count,
            "hold_key": self.hold_key,
            "delay_ms": self.delay_ms,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ScriptStep:
        kind = str(data.get("kind", "click"))
        button = str(data.get("mouse_button", "left")).lower()
        if button not in MOUSE_BUTTONS:
            button = "left"
        return cls(
            kind=kind if kind in ("click", "delay") else "click",
            x=int(data.get("x", 0) or 0),
            y=int(data.get("y", 0) or 0),
            mouse_button=button,
            interval_ms=max(1, int(data.get("interval_ms", 200) or 200)),
            click_count=max(1, int(data.get("click_count", 1) or 1)),
            hold_key=_normalize_hold_key(data.get("hold_key", "")),
            delay_ms=max(0, int(data.get("delay_ms", 1000) or 0)),
        )

    def summary(self) -> str:
        if self.kind == "delay":
            return f"Пауза {self.delay_ms} мс"
        btn = MOUSE_BUTTON_LABELS.get(self.mouse_button, self.mouse_button)
        hold_label = HOLD_KEY_LABELS.get(self.hold_key, self.hold_key)
        hold = f", hold [{hold_label}]" if self.hold_key else ""
        return (
            f"Клик {btn} @ ({self.x}, {self.y}) x{self.click_count} "
            f"каждые {self.interval_ms} мс{hold}"
        )


def _normalize_hold_key(value: Any) -> str:
    key = str(value or "").strip().lower()
    if key in ("capslock", "caps"):
        key = "caps lock"
    return key if key in ALLOWED_HOLD_KEYS else ""


@dataclass
class ClickScript:
    id: str = field(default_factory=lambda: uuid4().hex[:10])
    name: str = "Новый скрипт"
    hotkey: str = ""
    loop: bool = False
    steps: List[ScriptStep] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "hotkey": self.hotkey,
            "loop": self.loop,
            "steps": [step.to_dict() for step in self.steps],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ClickScript:
        steps = [
            ScriptStep.from_dict(item)
            for item in data.get("steps", [])
            if isinstance(item, dict)
        ]
        return cls(
            id=str(data.get("id") or uuid4().hex[:10]),
            name=str(data.get("name") or "Скрипт"),
            hotkey=str(data.get("hotkey") or "").strip().lower(),
            loop=bool(data.get("loop", False)),
            steps=steps,
        )
