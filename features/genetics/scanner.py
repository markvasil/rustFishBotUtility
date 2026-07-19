"""Click-triggered gene scanning via rustGensAIVision (GeneReader + auto-detect)."""

from __future__ import annotations

import ctypes
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

import mss
import numpy as np

_VISION_ROOT = Path(__file__).resolve().parents[2] / "rustGensAIVision"
if _VISION_ROOT.is_dir() and str(_VISION_ROOT) not in sys.path:
    sys.path.insert(0, str(_VISION_ROOT))

DEFAULT_MODEL_PATH = _VISION_ROOT / "artifacts" / "gene_slot.onnx"
MIN_AVG_CONFIDENCE = 0.55
CLICK_POLL_SEC = 0.02
# После отпускания ЛКМ ждём появления UI генов и пробуем несколько раз.
POST_CLICK_SETTLE_SEC = 0.50
READ_RETRY_COUNT = 8
READ_RETRY_INTERVAL_SEC = 0.10

VK_LBUTTON = 0x01
_user32 = ctypes.windll.user32

ScanCallback = Callable[[str, str], None]
StatusCallback = Callable[[str], None]


def _grab_monitor_bgr(sct: mss.mss, monitor_index: int = 1) -> np.ndarray:
    import cv2

    mon = sct.monitors[monitor_index]
    shot = np.array(sct.grab(mon))
    return cv2.cvtColor(shot, cv2.COLOR_BGRA2BGR)


def _is_lmb_down() -> bool:
    return bool(_user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)


class GeneScanner:
    """Background loop: wait LMB click → capture → GeneReader.read(auto_detect) → callback."""

    def __init__(
        self,
        on_gene_found: ScanCallback,
        on_status: Optional[StatusCallback] = None,
        *,
        model_path: Optional[Path] = None,
        monitor_index: int = 1,
    ) -> None:
        self._on_gene_found = on_gene_found
        self._on_status = on_status or (lambda _msg: None)
        self._model_path = Path(model_path) if model_path else DEFAULT_MODEL_PATH
        self._monitor_index = monitor_index

        self._reader = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._load_error: Optional[str] = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _ensure_reader(self) -> bool:
        if self._reader is not None:
            return True
        if self._load_error:
            self._on_status(self._load_error)
            return False
        if not self._model_path.is_file():
            self._load_error = (
                f"Модель не найдена: {self._model_path.name}. "
                "Обучите/экспортируйте ONNX в rustGensAIVision/artifacts/ (см. README сабмодуля)."
            )
            self._on_status(self._load_error)
            return False
        try:
            from rust_gens_vision import GeneReader

            self._reader = GeneReader(self._model_path)
        except Exception as exc:  # noqa: BLE001
            self._load_error = f"Не удалось загрузить GeneReader: {exc}"
            self._on_status(self._load_error)
            return False
        return True

    def start(self) -> None:
        if self.is_running:
            return
        if not self._ensure_reader():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="GeneScanner")
        self._thread.start()
        self._on_status("Кликните ЛКМ по гену в Rust")

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=2.0)
        self._thread = None
        self._on_status("Сканирование остановлено")

    def stop_async(self, on_stopped: Optional[Callable[[], None]] = None) -> None:
        def waiter() -> None:
            self.stop()
            if on_stopped:
                on_stopped()

        threading.Thread(target=waiter, daemon=True, name="GeneScannerStop").start()

    def _wait_while(self, pressed: bool) -> bool:
        """Wait while LMB matches `pressed`. Returns False if stop was requested."""
        while not self._stop.is_set():
            if _is_lmb_down() != pressed:
                return True
            time.sleep(CLICK_POLL_SEC)
        return False

    def _wait_full_click(self) -> bool:
        """Wait for press+release. Returns False if stop was requested."""
        if not self._wait_while(pressed=False):
            return False
        if self._stop.is_set():
            return False
        return self._wait_while(pressed=True)

    def _try_read(self, sct: mss.mss):
        """Capture and classify; retry briefly while gene UI may still be appearing."""
        assert self._reader is not None
        last_pred = None
        for attempt in range(READ_RETRY_COUNT):
            if self._stop.is_set():
                return None
            if attempt == 0:
                time.sleep(POST_CLICK_SETTLE_SEC)
            else:
                time.sleep(READ_RETRY_INTERVAL_SEC)

            frame = _grab_monitor_bgr(sct, self._monitor_index)
            pred = self._reader.read(frame, auto_detect=True)
            last_pred = pred
            if not (pred.found and pred.genome):
                continue
            avg_conf = sum(pred.confidences) / len(pred.confidences) if pred.confidences else 0.0
            if avg_conf >= MIN_AVG_CONFIDENCE:
                return pred
        return last_pred

    def _run_loop(self) -> None:
        assert self._reader is not None
        with mss.mss() as sct:
            if self._monitor_index < 0 or self._monitor_index >= len(sct.monitors):
                self._on_status(f"Неверный монитор: {self._monitor_index}")
                return

            # Игнорируем ЛКМ от нажатия кнопки «Сканировать».
            if not self._wait_while(pressed=True):
                return

            while not self._stop.is_set():
                self._on_status("Кликните ЛКМ по гену в Rust")
                if not self._wait_full_click():
                    return
                if self._stop.is_set():
                    return

                self._on_status("Считываем ген…")
                try:
                    pred = self._try_read(sct)
                except Exception as exc:  # noqa: BLE001
                    self._on_status(f"Ошибка скана: {exc}. Кликните снова")
                    continue

                if pred is None:
                    continue

                if pred.found and pred.genome:
                    avg_conf = (
                        sum(pred.confidences) / len(pred.confidences) if pred.confidences else 0.0
                    )
                    if avg_conf >= MIN_AVG_CONFIDENCE:
                        self._on_gene_found(pred.genome, "click")
                        # Не затираем «Найдено» сразу — пауза до следующего ожидания клика.
                        time.sleep(0.35)
                    else:
                        self._on_status(
                            f"Низкая уверенность ({avg_conf:.0%}). Кликните снова"
                        )
                        time.sleep(0.6)
                else:
                    self._on_status("Ген не найден. Наведите на строку генов и кликните снова")
                    time.sleep(0.6)
