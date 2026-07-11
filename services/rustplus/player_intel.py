from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app_paths import get_rustplus_dir


class PlayerIntelDB:
    """Локальная БД онлайна команды (без Battlemetrics / подписок)."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = path or (get_rustplus_dir() / "player_intel.db")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS online_samples (
                    steam_id INTEGER NOT NULL,
                    server_id TEXT NOT NULL,
                    ts INTEGER NOT NULL,
                    is_online INTEGER NOT NULL,
                    PRIMARY KEY (steam_id, server_id, ts)
                )
                """
            )
            conn.commit()

    def record_team(self, server_id: str, members: List[Dict[str, Any]]) -> None:
        ts = int(time.time())
        with sqlite3.connect(self._path) as conn:
            for member in members:
                steam_id = int(member.get("steam_id", 0))
                if not steam_id:
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO online_samples (steam_id, server_id, ts, is_online) VALUES (?, ?, ?, ?)",
                    (steam_id, server_id, ts, 1 if member.get("is_online") else 0),
                )
            conn.commit()

    def heatmap(self, server_id: str, steam_id: int, weeks: int = 12) -> Dict[int, int]:
        cutoff = int(time.time()) - weeks * 7 * 24 * 3600
        buckets: Dict[int, int] = {h: 0 for h in range(24)}
        with sqlite3.connect(self._path) as conn:
            rows = conn.execute(
                """
                SELECT ts, is_online FROM online_samples
                WHERE server_id = ? AND steam_id = ? AND ts >= ?
                ORDER BY ts
                """,
                (server_id, steam_id, cutoff),
            ).fetchall()
        for ts, is_online in rows:
            if is_online:
                hour = time.localtime(ts).tm_hour
                buckets[hour] = buckets.get(hour, 0) + 1
        return buckets

    def predict_online(self, server_id: str, steam_id: int) -> Optional[str]:
        heat = self.heatmap(server_id, steam_id)
        if not any(heat.values()):
            return None
        best_hour = max(heat, key=lambda h: heat[h])
        return f"Чаще онлайн около {best_hour:02d}:00–{(best_hour + 1) % 24:02d}:00 (локальное время)"
