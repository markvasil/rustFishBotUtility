from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import customtkinter as ctk

from features.base import Feature
from storage.session import SessionStore


@dataclass
class NoteEntry:
    title: str
    code: str
    note: str


class NotesFeature(Feature):
    id = "notes"
    title = "Заметки"

    def __init__(self, session: SessionStore) -> None:
        super().__init__()
        self._session = session
        self._entries: List[NoteEntry] = []
        self._title_var: Optional[ctk.StringVar] = None
        self._code_var: Optional[ctk.StringVar] = None
        self._note_var: Optional[ctk.StringVar] = None
        self._table_frame: Optional[ctk.CTkFrame] = None
        self._load()

    def _load(self) -> None:
        data = self._session.get_feature(self.id)
        self._entries = [
            NoteEntry(
                title=str(item.get("title", "")),
                code=str(item.get("code", "")),
                note=str(item.get("note", "")),
            )
            for item in data.get("entries", [])
        ]

    def _save(self) -> None:
        self._session.set_feature(
            self.id,
            {
                "entries": [
                    {"title": e.title, "code": e.code, "note": e.note}
                    for e in self._entries
                ]
            },
        )

    def build(self, parent: ctk.CTkFrame) -> None:
        self._title_var = ctk.StringVar(value="")
        self._code_var = ctk.StringVar(value="")
        self._note_var = ctk.StringVar(value="")

        ctk.CTkLabel(
            parent,
            text="Коды дверей и заметки по базам / рейдам",
            font=ctk.CTkFont(size=13),
            text_color="#a0a8b8",
        ).pack(anchor="w", padx=12, pady=(12, 8))

        form = ctk.CTkFrame(parent, fg_color="#1a2030", corner_radius=8)
        form.pack(fill="x", padx=12, pady=(0, 8))

        for label, var, width in [
            ("Название:", self._title_var, 200),
            ("Код:", self._code_var, 100),
            ("Заметка:", self._note_var, 260),
        ]:
            row = ctk.CTkFrame(form, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=4)
            ctk.CTkLabel(row, text=label, width=80, anchor="w").pack(side="left")
            ctk.CTkEntry(row, textvariable=var, width=width).pack(side="left", padx=(4, 0))

        buttons = ctk.CTkFrame(form, fg_color="transparent")
        buttons.pack(fill="x", padx=10, pady=(6, 10))

        ctk.CTkButton(
            buttons, text="+ Добавить", width=120,
            fg_color="#c45c26", hover_color="#a04a1e", command=self._add_entry,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            buttons, text="Очистить", width=100,
            fg_color="#3d4659", hover_color="#4d5669", command=self._clear_entries,
        ).pack(side="left")

        self._table_frame = ctk.CTkFrame(parent, fg_color="#10151f", corner_radius=6)
        self._table_frame.pack(fill="x", padx=12, pady=(0, 12))
        self._refresh()

    def _add_entry(self) -> None:
        title = self._title_var.get().strip() if self._title_var else ""
        code = self._code_var.get().strip() if self._code_var else ""
        note = self._note_var.get().strip() if self._note_var else ""
        if not title and not code and not note:
            return
        self._entries.append(NoteEntry(title=title or "Без названия", code=code, note=note))
        self._save()
        self._refresh()

    def _remove_entry(self, index: int) -> None:
        if 0 <= index < len(self._entries):
            del self._entries[index]
            self._save()
            self._refresh()

    def _clear_entries(self) -> None:
        self._entries.clear()
        self._save()
        self._refresh()

    def _refresh(self) -> None:
        if not self._table_frame:
            return
        for w in self._table_frame.winfo_children():
            w.destroy()
        if not self._entries:
            ctk.CTkLabel(
                self._table_frame, text="Нет заметок. Добавьте код двери или заметку.",
                text_color="#6b7280",
            ).pack(pady=20)
        else:
            for i, entry in enumerate(self._entries):
                row = ctk.CTkFrame(self._table_frame, fg_color="#161c2a", corner_radius=4)
                row.pack(fill="x", pady=2)
                text = f"{entry.title}"
                if entry.code:
                    text += f"  |  Код: {entry.code}"
                if entry.note:
                    text += f"  |  {entry.note}"
                ctk.CTkLabel(row, text=text, anchor="w", font=ctk.CTkFont(size=12),
                             text_color="#d1d7e3").pack(side="left", fill="x", expand=True, padx=8, pady=6)
                ctk.CTkButton(row, text="✕", width=28, height=28,
                              fg_color="#4a2230", hover_color="#6a2f42",
                              command=lambda idx=i: self._remove_entry(idx)).pack(side="right", padx=4)
        self.request_resize()
