from __future__ import annotations

import ctypes
import threading
import time
from typing import Callable, Optional

import keyboard

from features.click_scripts.models import ClickScript, ScriptStep

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040

_BUTTON_FLAGS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}


def _click_at(x: int, y: int, button: str = "left") -> None:
    user32 = ctypes.windll.user32
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.008)
    down, up = _BUTTON_FLAGS.get(button, _BUTTON_FLAGS["left"])
    user32.mouse_event(down, 0, 0, 0, 0)
    time.sleep(0.008)
    user32.mouse_event(up, 0, 0, 0, 0)


def _press_key(key: str) -> None:
    if not key:
        return
    try:
        keyboard.press(key)
    except Exception:
        pass


def _release_key(key: str) -> None:
    if not key:
        return
    try:
        keyboard.release(key)
    except Exception:
        pass


class ScriptEngine:
    """Фоновый исполнитель скриптов кликов."""

    def __init__(
        self,
        on_status: Optional[Callable[[str], None]] = None,
        on_finished: Optional[Callable[[], None]] = None,
    ) -> None:
        self._on_status = on_status
        self._on_finished = on_finished
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._running_id: Optional[str] = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def running_script_id(self) -> Optional[str]:
        return self._running_id if self.is_running else None

    def start(self, script: ClickScript) -> bool:
        with self._lock:
            if self.is_running:
                self._stop.set()
                thread = self._thread
                if thread is not None:
                    thread.join(timeout=1.5)
            if self.is_running:
                self._emit_status("Не удалось остановить предыдущий скрипт")
                return False
            if not script.steps:
                self._emit_status("Нет шагов в скрипте")
                return False
            self._stop.clear()
            self._running_id = script.id
            self._thread = threading.Thread(
                target=self._run,
                args=(script,),
                name=f"click-script-{script.id}",
                daemon=True,
            )
            self._thread.start()
            return True

    def stop(self) -> None:
        self._stop.set()

    def _emit_status(self, message: str) -> None:
        if self._on_status:
            try:
                self._on_status(message)
            except Exception:
                pass

    def _emit_finished(self) -> None:
        if self._on_finished:
            try:
                self._on_finished()
            except Exception:
                pass

    def _wait(self, ms: int) -> bool:
        """Ждёт ms миллисекунд. False если остановлен."""
        if ms <= 0:
            return not self._stop.is_set()
        return not self._stop.wait(ms / 1000.0)

    def _run_click_step(self, step: ScriptStep, index: int, total: int) -> bool:
        hold = step.hold_key
        self._emit_status(
            f"Шаг {index}/{total}: клик ({step.x}, {step.y})"
            + (f", hold {hold}" if hold else "")
        )
        _press_key(hold)
        try:
            for n in range(step.click_count):
                if self._stop.is_set():
                    return False
                try:
                    _click_at(step.x, step.y, step.mouse_button)
                except Exception:
                    pass
                if n + 1 >= step.click_count:
                    break
                if not self._wait(step.interval_ms):
                    return False
        finally:
            _release_key(hold)
        return not self._stop.is_set()

    def _run_delay_step(self, step: ScriptStep, index: int, total: int) -> bool:
        self._emit_status(f"Шаг {index}/{total}: пауза {step.delay_ms} мс")
        return self._wait(step.delay_ms)

    def _run(self, script: ClickScript) -> None:
        self._emit_status(f"Скрипт «{script.name}» запущен")
        try:
            while not self._stop.is_set():
                for i, step in enumerate(script.steps, start=1):
                    if self._stop.is_set():
                        break
                    ok = (
                        self._run_delay_step(step, i, len(script.steps))
                        if step.kind == "delay"
                        else self._run_click_step(step, i, len(script.steps))
                    )
                    if not ok:
                        break
                else:
                    if script.loop and not self._stop.is_set():
                        continue
                break
        finally:
            self._running_id = None
            stopped = self._stop.is_set()
            self._emit_status(
                f"Скрипт «{script.name}» {'остановлен' if stopped else 'завершён'}"
            )
            self._emit_finished()
