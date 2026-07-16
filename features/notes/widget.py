from __future__ import annotations

from typing import Optional

import customtkinter as ctk

from features.base import Feature
from storage.session import SessionStore


class NotesFeature(Feature):
    id = "notes"
    title = "Заметки"

    def __init__(self, session: SessionStore) -> None:
        super().__init__()
        self._session = session
        self._text: Optional[ctk.CTkTextbox] = None
        self._save_job: Optional[str] = None
        self._content = self._load_content()

    def _load_content(self) -> str:
        data = self._session.get_feature(self.id)
        if isinstance(data.get("text"), str):
            return data["text"]

        # Миграция старого формата entries → единый текст
        entries = data.get("entries")
        if isinstance(entries, list) and entries:
            lines: list[str] = []
            for item in entries:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title", "")).strip()
                code = str(item.get("code", "")).strip()
                note = str(item.get("note", "")).strip()
                parts = [p for p in (title, f"код {code}" if code else "", note) if p]
                if parts:
                    lines.append(" — ".join(parts))
            return "\n".join(lines)
        return ""

    def _save(self, text: Optional[str] = None) -> None:
        if text is None and self._text is not None:
            text = self._text.get("1.0", "end-1c")
        if text is None:
            text = self._content
        self._content = text
        self._session.set_feature(self.id, {"text": text})

    def build(self, parent: ctk.CTkFrame) -> None:
        ctk.CTkLabel(
            parent,
            text="Свободные заметки",
            font=ctk.CTkFont(size=13),
            text_color="#a0a8b8",
        ).pack(anchor="w", padx=12, pady=(12, 8))

        self._text = ctk.CTkTextbox(
            parent,
            width=560,
            height=320,
            corner_radius=8,
            fg_color="#1a2030",
            text_color="#e8ecf4",
            font=ctk.CTkFont(size=13),
            wrap="word",
            border_width=1,
            border_color="#2a3142",
        )
        self._text.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        if self._content:
            self._text.insert("1.0", self._content)

        self._text.bind("<KeyRelease>", self._on_text_changed)
        self._text.bind("<<Paste>>", self._on_text_changed)
        self._text.bind("<<Cut>>", self._on_text_changed)

    def _on_text_changed(self, _event=None) -> None:
        if self._save_job and self._text is not None:
            try:
                self._text.after_cancel(self._save_job)
            except Exception:
                pass
        if self._text is not None:
            self._save_job = self._text.after(400, self._save)

    def on_hide(self) -> None:
        if self._save_job and self._text is not None:
            try:
                self._text.after_cancel(self._save_job)
            except Exception:
                pass
            self._save_job = None
        self._save()

    def on_shutdown(self) -> None:
        self.on_hide()
