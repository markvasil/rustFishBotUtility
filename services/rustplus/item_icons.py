from __future__ import annotations

import json
import re
import threading
import time
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional

from PIL import Image

from app_paths import get_rustplus_dir

ITEMS_MD_URL = "https://raw.githubusercontent.com/olijeffers0n/RustItems/master/data/items.md"
EXTENDED_ITEMS_URL = (
    "https://raw.githubusercontent.com/SzyMig/Rust-item-list-JSON/main/Rust-Items.json"
)
CDN_URL = "https://cdn.rusthelp.com/images/256/{slug}.webp"
USER_AGENT = "Mozilla/5.0 (RustUtilityOverlay)"
EXTENDED_CACHE_MAX_AGE_SEC = 7 * 24 * 3600


class ItemIconCache:
    """Кэш иконок предметов Rust (item_id → картинка)."""

    def __init__(self, cache_dir: Optional[Path] = None) -> None:
        base = cache_dir or (get_rustplus_dir() / "item_icons")
        self._dir = base
        self._dir.mkdir(parents=True, exist_ok=True)
        self._slug_path = get_rustplus_dir() / "item_slugs.json"
        self._extended_path = get_rustplus_dir() / "extended_items.json"
        self._memory: Dict[int, Image.Image] = {}
        self._slugs: Dict[int, str] = {}
        self._names: Dict[int, str] = {}
        self._shortnames: Dict[int, str] = {}
        self._loading: set[int] = set()
        self._slug_lock = threading.Lock()
        self._catalog_refreshing = False
        self._load_local_catalog()

    def refresh_catalog_async(self) -> None:
        if getattr(self, "_catalog_refreshing", False):
            return
        self._catalog_refreshing = True

        def worker() -> None:
            try:
                self._merge_items_md()
                self._ensure_extended_catalog(force=False)
                self._merge_rustplus_names()
                self._persist_slugs()
            finally:
                self._catalog_refreshing = False

        threading.Thread(target=worker, daemon=True, name="ItemIconCatalog").start()

    def item_name(self, item_id: int) -> str:
        item_id = int(item_id)
        if item_id in self._names:
            return self._names[item_id]

        from rustplus.utils.grab_items import translate_id_to_stack

        name = translate_id_to_stack(item_id)
        if name != "Not Found":
            self._names[item_id] = name
            return name
        return "Неизвестный предмет"

    def fallback_glyph(self, item_id: int) -> str:
        name = self.item_name(item_id).strip()
        if not name or name == "Неизвестный предмет":
            return "?"
        letter = name[0].upper()
        return letter if letter.isalnum() else "?"

    def fetch_async(self, item_id: int, on_ready: Callable[[int, Image.Image], None]) -> None:
        item_id = int(item_id)
        cached = self.get(item_id)
        if cached is not None:
            on_ready(item_id, cached)
            return
        if item_id in self._loading:
            return
        self._loading.add(item_id)

        def worker() -> None:
            try:
                image = self._download(item_id)
                if image:
                    on_ready(item_id, image)
            finally:
                self._loading.discard(item_id)

        threading.Thread(target=worker, daemon=True).start()

    def get(self, item_id: int) -> Optional[Image.Image]:
        item_id = int(item_id)
        if item_id in self._memory:
            return self._memory[item_id]
        path = self._icon_path(item_id)
        if path.exists():
            try:
                image = Image.open(path).convert("RGBA")
                self._memory[item_id] = image
                return image
            except Exception:
                pass
        return None

    def _icon_path(self, item_id: int) -> Path:
        return self._dir / f"{item_id}.webp"

    def _download(self, item_id: int) -> Optional[Image.Image]:
        item_id = int(item_id)
        existing = self.get(item_id)
        if existing:
            return existing

        for slug in self._slug_candidates(item_id):
            image = self._download_slug(item_id, slug)
            if image:
                self._remember_slug(item_id, slug)
                return image
        return None

    def _download_slug(self, item_id: int, slug: str) -> Optional[Image.Image]:
        url = CDN_URL.format(slug=slug)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = resp.read()
            path = self._icon_path(item_id)
            path.write_bytes(data)
            image = Image.open(path).convert("RGBA")
            self._memory[item_id] = image
            return image
        except Exception:
            return None

    def _slug_candidates(self, item_id: int) -> List[str]:
        item_id = int(item_id)
        candidates: List[str] = []

        def add(slug: Optional[str]) -> None:
            if slug and slug not in candidates:
                candidates.append(slug)

        add(self._slugs.get(item_id))

        shortname = self._shortnames.get(item_id)
        if shortname:
            add(shortname.replace(".", "-"))

        name = self._names.get(item_id)
        if name:
            add(self._name_to_slug(name))

        if not candidates:
            self._ensure_extended_catalog(force=False)
            add(self._slugs.get(item_id))
            shortname = self._shortnames.get(item_id)
            if shortname:
                add(shortname.replace(".", "-"))
            name = self._names.get(item_id)
            if name:
                add(self._name_to_slug(name))

        return candidates

    def _remember_slug(self, item_id: int, slug: str) -> None:
        with self._slug_lock:
            if self._slugs.get(item_id) == slug:
                return
            self._slugs[item_id] = slug
            self._persist_slugs()

    def _load_local_catalog(self) -> None:
        if self._slug_path.exists():
            try:
                raw = json.loads(self._slug_path.read_text(encoding="utf-8"))
                self._slugs = {int(k): str(v) for k, v in raw.items()}
            except Exception:
                self._slugs = {}
        cached = self._read_extended_items()
        if cached:
            self._merge_extended_items(cached)
        self._merge_rustplus_names()

    def _load_catalog(self) -> None:
        self._load_local_catalog()
        self._merge_items_md()
        self._ensure_extended_catalog(force=False)
        self._merge_rustplus_names()
        self._persist_slugs()

    def _merge_items_md(self) -> None:
        slugs = self._fetch_slugs_from_items_md()
        if slugs:
            self._slugs.update(slugs)

    def _merge_rustplus_names(self) -> None:
        try:
            from rustplus.utils.grab_items import item_ids
        except Exception:
            return

        for raw_id, name in item_ids.items():
            item_id = int(raw_id)
            self._names.setdefault(item_id, str(name))

    def _ensure_extended_catalog(self, force: bool) -> None:
        if not force and self._extended_path.exists():
            age = time.time() - self._extended_path.stat().st_mtime
            if age < EXTENDED_CACHE_MAX_AGE_SEC:
                self._merge_extended_items(self._read_extended_items())
                return

        payload = self._fetch_extended_items()
        if payload:
            try:
                self._extended_path.write_text(
                    json.dumps(payload, ensure_ascii=False),
                    encoding="utf-8",
                )
            except OSError:
                pass
            self._merge_extended_items(payload)
            return

        cached = self._read_extended_items()
        if cached:
            self._merge_extended_items(cached)

    def _read_extended_items(self) -> list:
        if not self._extended_path.exists():
            return []
        try:
            data = json.loads(self._extended_path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _merge_extended_items(self, items: list) -> None:
        for entry in items:
            if not isinstance(entry, dict):
                continue
            try:
                item_id = int(entry.get("itemid"))
            except (TypeError, ValueError):
                continue

            shortname = str(entry.get("shortname") or "").strip()
            name = str(entry.get("Name") or entry.get("name") or "").strip()

            if name:
                self._names.setdefault(item_id, name)
            if shortname:
                self._shortnames.setdefault(item_id, shortname)
                self._slugs.setdefault(item_id, shortname.replace(".", "-"))

    def _persist_slugs(self) -> None:
        if not self._slugs:
            return
        try:
            self._slug_path.write_text(
                json.dumps(self._slugs, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _fetch_slugs_from_items_md(self) -> Dict[int, str]:
        try:
            req = urllib.request.Request(ITEMS_MD_URL, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=20) as resp:
                text = resp.read().decode("utf-8", errors="replace")
        except Exception:
            return {}

        slugs: Dict[int, str] = {}
        for line in text.splitlines():
            if not line.startswith("|") or "rustlabs.com" not in line:
                continue
            parts = [part.strip() for part in line.split("|")[1:-1]]
            if len(parts) < 3 or not parts[2].lstrip("-").isdigit():
                continue
            match = re.search(r"items40/([^)]+)\.png", parts[1])
            if not match:
                continue
            item_id = int(parts[2])
            slugs[item_id] = match.group(1).replace(".", "-")
            if parts[0]:
                self._names.setdefault(item_id, parts[0])
        return slugs

    def _fetch_extended_items(self) -> list:
        try:
            req = urllib.request.Request(EXTENDED_ITEMS_URL, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    @staticmethod
    def _name_to_slug(name: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        return slug
