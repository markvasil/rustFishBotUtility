"""Тихие UI-звуки оверлея (без резких Beep)."""

from __future__ import annotations

import io
import math
import random
import struct
import threading
import wave
import winsound
from pathlib import Path
from typing import Optional

from app_paths import get_rustplus_dir


def _minecraft_pop_wav(volume: float = 0.32) -> bytes:
    """
    Короткий 'чпок' в духе Minecraft bubble pop:
    щелчок шума + тон с быстрым падением высоты.
    (синтез, без ассетов Mojang)
    """
    rate = 44100
    duration = 0.09
    n_samples = int(rate * duration)
    rng = random.Random(42)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)

        frames = bytearray()
        phase = 0.0
        for i in range(n_samples):
            t = i / rate
            freq = 1100.0 * math.exp(-t * 32.0) + 90.0
            phase += 2.0 * math.pi * freq / rate
            tone = math.sin(phase) + 0.18 * math.sin(phase * 2.0)

            noise = rng.uniform(-1.0, 1.0)
            noise_env = math.exp(-t * 95.0)
            tone_env = math.exp(-t * 24.0) * min(1.0, t * 450.0)

            mixed = 0.62 * tone * tone_env + 0.28 * noise * noise_env
            value = int(max(-1.0, min(1.0, mixed * volume)) * 32767)
            frames += struct.pack("<h", value)

        wf.writeframes(frames)
    return buf.getvalue()


_WAV_PATH: Optional[Path] = None


def _ensure_wav_file() -> Path:
    global _WAV_PATH
    if _WAV_PATH is not None and _WAV_PATH.exists():
        return _WAV_PATH
    path = get_rustplus_dir() / "ui_soft_pop.wav"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_minecraft_pop_wav())
    _WAV_PATH = path
    return path


def play_soft_pop() -> None:
    """
    Тихий майнкрафтоподобный чпок.

    На Windows SND_MEMORY|SND_ASYNC часто падает и тогда играет
    системный звук — поэтому пишем WAV на диск и играем из файла.
    """
    try:
        path = _ensure_wav_file()
        flags = winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
        winsound.PlaySound(str(path), flags)
    except Exception:
        # запасной путь: sync из памяти в фоне (без системного MessageBeep)
        try:
            data = _minecraft_pop_wav()

            def _play() -> None:
                try:
                    winsound.PlaySound(data, winsound.SND_MEMORY | winsound.SND_NODEFAULT)
                except Exception:
                    pass

            threading.Thread(target=_play, daemon=True).start()
        except Exception:
            pass
