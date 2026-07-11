from __future__ import annotations

from typing import Dict, List, Optional

import customtkinter as ctk

from features.base import Feature
from features.craft_calculator.calculator import (
    CraftEntry,
    calculate_craft_summary,
    create_entry,
)
from features.furnace_calculator.calculator import format_duration
from features.raid_calculator.data import EXPLOSIVES, EXPLOSIVE_BY_ID


from storage.session import SessionStore


class CraftCalculatorFeature(Feature):
    id = "craft_calculator"
    title = "Калькулятор крафта"

    def __init__(self, session: SessionStore) -> None:
        super().__init__()
        self._session = session
        self._entries: List[CraftEntry] = []
        self._explosive_var: Optional[ctk.StringVar] = None
        self._count_var: Optional[ctk.StringVar] = None
        self._table_frame: Optional[ctk.CTkFrame] = None
        self._refined_frame: Optional[ctk.CTkFrame] = None
        self._raw_frame: Optional[ctk.CTkFrame] = None
        self._furnace_frame: Optional[ctk.CTkFrame] = None
        self._furnace_time_label: Optional[ctk.CTkLabel] = None
        self._other_frame: Optional[ctk.CTkFrame] = None

    def build(self, parent: ctk.CTkFrame) -> None:
        self._explosive_var = ctk.StringVar(value="")
        self._count_var = ctk.StringVar(value="1")

        header = ctk.CTkLabel(
            parent,
            text="Взрывчатка → ресурсы для крафта с учётом плавки в печи",
            font=ctk.CTkFont(size=13),
            text_color="#a0a8b8",
        )
        header.pack(anchor="w", padx=12, pady=(12, 8))

        form = ctk.CTkFrame(parent, fg_color="#1a2030", corner_radius=8)
        form.pack(fill="x", padx=12, pady=(0, 8))

        row1 = ctk.CTkFrame(form, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=(10, 6))

        ctk.CTkLabel(row1, text="Взрывчатка:", width=100, anchor="w").pack(side="left")
        explosive_names = [e.name for e in EXPLOSIVES]
        self._explosive_var.set(explosive_names[0])
        ctk.CTkOptionMenu(
            row1,
            variable=self._explosive_var,
            values=explosive_names,
            width=300,
            fg_color="#2a3142",
            button_color="#3d4659",
        ).pack(side="left", padx=(4, 0))

        row2 = ctk.CTkFrame(form, fg_color="transparent")
        row2.pack(fill="x", padx=10, pady=(6, 10))

        ctk.CTkLabel(row2, text="Кол-во:", width=100, anchor="w").pack(side="left")
        ctk.CTkEntry(row2, textvariable=self._count_var, width=70).pack(side="left", padx=(4, 12))

        ctk.CTkButton(
            row2,
            text="+ Добавить",
            width=120,
            fg_color="#c45c26",
            hover_color="#a04a1e",
            command=self._add_entry,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            row2,
            text="Очистить",
            width=100,
            fg_color="#3d4659",
            hover_color="#4d5669",
            command=self._clear_entries,
        ).pack(side="left")

        table_header = ctk.CTkFrame(parent, fg_color="#141a28", corner_radius=6)
        table_header.pack(fill="x", padx=12, pady=(4, 0))

        for text, width in [("Взрывчатка", 280), ("Кол-во", 80), ("Сера", 90), ("", 36)]:
            ctk.CTkLabel(
                table_header,
                text=text,
                width=width,
                anchor="w",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#8b93a7",
            ).pack(side="left", padx=4, pady=6)

        self._table_frame = ctk.CTkFrame(parent, fg_color="#10151f", corner_radius=6)
        self._table_frame.pack(fill="x", padx=12, pady=(0, 8))

        resources = ctk.CTkFrame(parent, fg_color="transparent")
        resources.pack(fill="x", padx=12, pady=(0, 8))

        left = ctk.CTkFrame(resources, fg_color="#1a2030", corner_radius=8)
        left.pack(side="left", fill="x", expand=True, padx=(0, 4))

        right = ctk.CTkFrame(resources, fg_color="#1a2030", corner_radius=8)
        right.pack(side="left", fill="x", expand=True, padx=(4, 0))

        ctk.CTkLabel(
            left,
            text="Переработанные ресурсы",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#6ec1e4",
        ).pack(anchor="w", padx=12, pady=(10, 2))

        ctk.CTkLabel(
            left,
            text="Сера, металл, уголь, НКТ — уже после плавки",
            font=ctk.CTkFont(size=11),
            text_color="#6b7280",
        ).pack(anchor="w", padx=12, pady=(0, 6))

        self._refined_frame = ctk.CTkFrame(left, fg_color="transparent")
        self._refined_frame.pack(fill="x", padx=8, pady=(0, 8))

        ctk.CTkLabel(
            right,
            text="Сырьё",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#e8a838",
        ).pack(anchor="w", padx=12, pady=(10, 2))

        ctk.CTkLabel(
            right,
            text="Руда, дерево, нефть — с учётом печи",
            font=ctk.CTkFont(size=11),
            text_color="#6b7280",
        ).pack(anchor="w", padx=12, pady=(0, 6))

        self._raw_frame = ctk.CTkFrame(right, fg_color="transparent")
        self._raw_frame.pack(fill="x", padx=8, pady=(0, 8))

        furnace_section = ctk.CTkFrame(parent, fg_color="#1a2030", corner_radius=8)
        furnace_section.pack(fill="x", padx=12, pady=(0, 8))

        ctk.CTkLabel(
            furnace_section,
            text="Плавка в печи",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#c45c26",
        ).pack(anchor="w", padx=12, pady=(10, 2))

        ctk.CTkLabel(
            furnace_section,
            text="Дерево на руду + уголь с плавки (~75%) + доп. дерево при нехватке угля",
            font=ctk.CTkFont(size=11),
            text_color="#6b7280",
        ).pack(anchor="w", padx=12, pady=(0, 4))

        self._furnace_time_label = ctk.CTkLabel(
            furnace_section,
            text="Время плавки: 0 сек",
            font=ctk.CTkFont(size=12),
            text_color="#f0b429",
        )
        self._furnace_time_label.pack(anchor="w", padx=12, pady=(0, 6))

        self._furnace_frame = ctk.CTkFrame(furnace_section, fg_color="transparent")
        self._furnace_frame.pack(fill="x", padx=8, pady=(0, 10))

        other_section = ctk.CTkFrame(parent, fg_color="#1a2030", corner_radius=8)
        other_section.pack(fill="x", padx=12, pady=(0, 12))

        ctk.CTkLabel(
            other_section,
            text="Прочие компоненты",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#e8ecf4",
        ).pack(anchor="w", padx=12, pady=(10, 2))

        ctk.CTkLabel(
            other_section,
            text="HQM, ткань, микросхемы, трубы и т.д.",
            font=ctk.CTkFont(size=11),
            text_color="#6b7280",
        ).pack(anchor="w", padx=12, pady=(0, 6))

        self._other_frame = ctk.CTkFrame(other_section, fg_color="transparent")
        self._other_frame.pack(fill="x", padx=8, pady=(0, 10))

        self._load_saved()
        self._refresh()

    def _load_saved(self) -> None:
        for item in self._session.get_feature(self.id).get("entries", []):
            entry = create_entry(str(item.get("explosive_id", "")), int(item.get("count", 1)))
            if entry:
                self._entries.append(entry)

    def _save(self) -> None:
        self._session.set_feature(
            self.id,
            {
                "entries": [
                    {"explosive_id": e.explosive_id, "count": e.count}
                    for e in self._entries
                ]
            },
        )

    def _explosive_id_from_name(self, name: str) -> Optional[str]:
        for explosive in EXPLOSIVES:
            if explosive.name == name:
                return explosive.id
        return None

    def _parse_count(self) -> int:
        try:
            return max(1, int(self._count_var.get().strip()))
        except ValueError:
            return 1

    def _add_entry(self) -> None:
        explosive_id = self._explosive_id_from_name(self._explosive_var.get())
        if not explosive_id:
            return
        entry = create_entry(explosive_id, self._parse_count())
        if entry:
            self._entries.append(entry)
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
        if not self._table_frame or not self._refined_frame or not self._raw_frame:
            return

        for frame in (
            self._table_frame,
            self._refined_frame,
            self._raw_frame,
            self._furnace_frame,
            self._other_frame,
        ):
            if frame:
                for widget in frame.winfo_children():
                    widget.destroy()

        if not self._entries:
            ctk.CTkLabel(
                self._table_frame,
                text="Список пуст. Добавьте взрывчатку для расчёта.",
                text_color="#6b7280",
            ).pack(pady=20)
        else:
            for index, entry in enumerate(self._entries):
                self._render_row(index, entry)

        summary = calculate_craft_summary(self._entries)

        self._render_resource_grid(self._refined_frame, summary.refined_totals(), "#1e3a4f")
        self._render_resource_grid(self._raw_frame, summary.raw_totals(), "#3d3520")
        if self._furnace_frame:
            self._render_resource_grid(self._furnace_frame, summary.furnace_breakdown(), "#3d2a1f", horizontal=True)
        if self._furnace_time_label:
            self._furnace_time_label.configure(
                text=f"Время плавки: {format_duration(summary.furnace.smelt_seconds)}"
            )
        if self._other_frame:
            self._render_resource_grid(self._other_frame, summary.other_totals(), "#242b3d", horizontal=True)

        self.request_resize()

    def _render_row(self, index: int, entry: CraftEntry) -> None:
        assert self._table_frame is not None
        row = ctk.CTkFrame(self._table_frame, fg_color="#161c2a", corner_radius=4)
        row.pack(fill="x", pady=2)

        cells = [
            (entry.explosive.name, 280),
            (str(entry.count), 80),
            (str(entry.cost.sulfur), 90),
        ]
        for text, width in cells:
            ctk.CTkLabel(
                row,
                text=text,
                width=width,
                anchor="w",
                font=ctk.CTkFont(size=12),
                text_color="#d1d7e3",
            ).pack(side="left", padx=4, pady=6)

        ctk.CTkButton(
            row,
            text="✕",
            width=28,
            height=28,
            fg_color="#4a2230",
            hover_color="#6a2f42",
            command=lambda i=index: self._remove_entry(i),
        ).pack(side="left", padx=4)

    def _render_resource_grid(
        self,
        parent: ctk.CTkFrame,
        totals: Dict[str, int],
        bg_color: str,
        horizontal: bool = False,
    ) -> None:
        if not totals:
            ctk.CTkLabel(parent, text="—", text_color="#6b7280").pack(anchor="w", padx=4, pady=4)
            return

        grid = ctk.CTkFrame(parent, fg_color="transparent")
        grid.pack(fill="x")

        col = 0
        row = 0
        max_cols = 4 if horizontal else 2

        for label, value in totals.items():
            item = ctk.CTkFrame(grid, fg_color=bg_color, corner_radius=6)
            item.grid(row=row, column=col, padx=4, pady=4, sticky="ew")
            ctk.CTkLabel(
                item,
                text=f"x{value}",
                font=ctk.CTkFont(size=15, weight="bold"),
                text_color="#f0b429",
            ).pack(padx=10, pady=(6, 0))
            ctk.CTkLabel(
                item,
                text=label,
                font=ctk.CTkFont(size=11),
                text_color="#9aa3b5",
            ).pack(padx=10, pady=(0, 6))
            col += 1
            if col >= max_cols:
                col = 0
                row += 1
