from __future__ import annotations

import json
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Optional

from PIL import Image

from app_paths import get_rustplus_dir


class SteamAvatarCache:
    """Кэш аватарок Steam для карты."""

    def __init__(self, cache_dir: Optional[Path] = None) -> None:
        self._dir = cache_dir or (get_rustplus_dir() / "avatars")
        self._dir.mkdir(parents=True, exist_ok=True)
        self._memory: Dict[int, Image.Image] = {}

    def get(self, steam_id: int) -> Optional[Image.Image]:
        steam_id = int(steam_id)
        if steam_id in self._memory:
            return self._memory[steam_id]
        path = self._dir / f"{steam_id}.jpg"
        if path.exists():
            try:
                img = Image.open(path).convert("RGBA")
                self._memory[steam_id] = img
                return img
            except Exception:
                pass
        return None

    def fetch_async(self, steam_id: int, on_ready) -> None:
        import threading

        def worker():
            img = self._download(steam_id)
            if img:
                on_ready(steam_id, img)

        threading.Thread(target=worker, daemon=True).start()

    def _download(self, steam_id: int) -> Optional[Image.Image]:
        steam_id = int(steam_id)
        path = self._dir / f"{steam_id}.jpg"
        if path.exists():
            try:
                img = Image.open(path).convert("RGBA")
                self._memory[steam_id] = img
                return img
            except Exception:
                pass
        try:
            url = f"https://steamcommunity.com/profiles/{steam_id}/?xml=1"
            with urllib.request.urlopen(url, timeout=8) as resp:
                xml_text = resp.read().decode("utf-8", errors="replace")
            root = ET.fromstring(xml_text)
            avatar_url = None
            for tag in ("avatarFull", "avatarMedium", "avatarIcon"):
                node = root.find(tag)
                if node is not None and node.text:
                    avatar_url = node.text.strip()
                    break
            if not avatar_url:
                return None
            with urllib.request.urlopen(avatar_url, timeout=8) as resp:
                data = resp.read()
            path.write_bytes(data)
            img = Image.open(path).convert("RGBA")
            self._memory[steam_id] = img
            return img
        except Exception:
            return None
