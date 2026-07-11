from __future__ import annotations

from typing import Dict, List, Optional

import customtkinter as ctk

from features.base import Feature
from features.raid_calculator.calculator import (
    RaidEntry,
    calculate_entry,
    calculate_raid,
    format_cost_short,
    format_duration,
    structures_by_category,
    available_explosives_for,
)
from features.raid_calculator.data import (
    CATEGORY_LABELS,
    EXPLOSIVE_BY_ID,
    RESOURCE_LABELS,
    STRUCTURE_BY_ID,
)


from storage.session import SessionStore


class RaidCalculatorFeature(Feature):
    id = "raid_calculator"
    title = "Калькулятор рейда"

    def __init__(self, session: SessionStore) -> None:
        super().__init__()
        self._session = session
        self._entries: List[RaidEntry] = []
        self._structure_var: Optional[ctk.StringVar] = None
        self._explosive_var: Optional[ctk.StringVar] = None
        self._count_var: Optional[ctk.StringVar] = None
        self._auto_var: Optional[ctk.BooleanVar] = None
        self._table_frame: Optional[ctk.CTkFrame] = None
        self._totals_frame: Optional[ctk.CTkFrame] = None
        self._time_label: Optional[ctk.CTkLabel] = None

    def build(self, parent: ctk.CTkFrame) -> None:
        self._structure_var = ctk.StringVar(value="")
        self._explosive_var = ctk.StringVar(value="")
        self._count_var = ctk.StringVar(value="1")
        self._auto_var = ctk.BooleanVar(value=True)

        header = ctk.CTkLabel(
            parent,
            text="Добавьте строения и получите стоимость рейда",
            font=ctk.CTkFont(size=13),
            text_color="#a0a8b8",
        )
        header.pack(anchor="w", padx=12, pady=(12, 8))

        form = ctk.CTkFrame(parent, fg_color="#1a2030", corner_radius=8)
        form.pack(fill="x", padx=12, pady=(0, 8))

        row1 = ctk.CTkFrame(form, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=(10, 6))

        ctk.CTkLabel(row1, text="Строение:", width=90, anchor="w").pack(side="left")
        structure_menu = ctk.CTkOptionMenu(
            row1,
            variable=self._structure_var,
            values=self._structure_options(),
            command=self._on_structure_change,
            width=280,
            fg_color="#2a3142",
            button_color="#3d4659",
        )
        structure_menu.pack(side="left", padx=(4, 0))

        row2 = ctk.CTkFrame(form, fg_color="transparent")
        row2.pack(fill="x", padx=10, pady=6)

        ctk.CTkLabel(row2, text="Кол-во:", width=90, anchor="w").pack(side="left")
        ctk.CTkEntry(row2, textvariable=self._count_var, width=70).pack(side="left", padx=(4, 12))

        auto_check = ctk.CTkCheckBox(
            row2,
            text="Авто (дешевле по сере)",
            variable=self._auto_var,
            command=self._on_auto_toggle,
            fg_color="#c45c26",
            hover_color="#a04a1e",
        )
        auto_check.pack(side="left")

        row3 = ctk.CTkFrame(form, fg_color="transparent")
        row3.pack(fill="x", padx=10, pady=(6, 10))

        ctk.CTkLabel(row3, text="Взрывчатка:", width=90, anchor="w").pack(side="left")
        self._explosive_menu = ctk.CTkOptionMenu(
            row3,
            variable=self._explosive_var,
            values=[""],
            width=280,
            fg_color="#2a3142",
            button_color="#3d4659",
        )
        self._explosive_menu.pack(side="left", padx=(4, 0))

        buttons = ctk.CTkFrame(form, fg_color="transparent")
        buttons.pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkButton(
            buttons,
            text="+ Добавить",
            width=120,
            fg_color="#c45c26",
            hover_color="#a04a1e",
            command=self._add_entry,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            buttons,
            text="Очистить",
            width=100,
            fg_color="#3d4659",
            hover_color="#4d5669",
            command=self._clear_entries,
        ).pack(side="left")

        table_header = ctk.CTkFrame(parent, fg_color="#141a28", corner_radius=6)
        table_header.pack(fill="x", padx=12, pady=(4, 0))

        for text, width in [
            ("Строение", 150),
            ("Кол-во", 50),
            ("Взрывчатка", 150),
            ("Кол-во", 55),
            ("Время", 80),
            ("Ресурсы", 220),
            ("", 36),
        ]:
            ctk.CTkLabel(
                table_header,
                text=text,
                width=width,
                anchor="w",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#8b93a7",
            ).pack(side="left", padx=4, pady=6)

        self._table_frame = ctk.CTkFrame(
            parent,
            fg_color="#10151f",
            corner_radius=6,
        )
        self._table_frame.pack(fill="x", padx=12, pady=(0, 8))

        summary = ctk.CTkFrame(parent, fg_color="#1a2030", corner_radius=8)
        summary.pack(fill="x", padx=12, pady=(0, 12))

        ctk.CTkLabel(
            summary,
            text="Итого",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#e8ecf4",
        ).pack(anchor="w", padx=12, pady=(10, 4))

        self._time_label = ctk.CTkLabel(
            summary,
            text="Общее время рейда: 0 сек",
            font=ctk.CTkFont(size=13),
            text_color="#f0b429",
        )
        self._time_label.pack(anchor="w", padx=12, pady=(0, 6))

        self._totals_frame = ctk.CTkFrame(summary, fg_color="transparent")
        self._totals_frame.pack(fill="x", padx=12, pady=(0, 12))

        self._set_default_structure()
        self._load_saved()
        self._refresh_table()

    def _load_saved(self) -> None:
        for item in self._session.get_feature(self.id).get("entries", []):
            entry = calculate_entry(
                str(item.get("structure_id", "")),
                int(item.get("structure_count", 1)),
                item.get("explosive_id"),
            )
            if entry:
                self._entries.append(entry)

    def _save(self) -> None:
        self._session.set_feature(
            self.id,
            {
                "entries": [
                    {
                        "structure_id": e.structure_id,
                        "structure_count": e.structure_count,
                        "explosive_id": e.explosive_id,
                    }
                    for e in self._entries
                ]
            },
        )

    def _structure_options(self) -> List[str]:
        options: List[str] = []
        for category, structures in structures_by_category().items():
            label = CATEGORY_LABELS.get(category, category)
            for structure in structures:
                options.append(f"{label} — {structure.name}")
        return options

    def _parse_structure_id(self, option: str) -> Optional[str]:
        for category, structures in structures_by_category().items():
            label = CATEGORY_LABELS.get(category, category)
            for structure in structures:
                if option == f"{label} — {structure.name}":
                    return structure.id
        return None

    def _set_default_structure(self) -> None:
        options = self._structure_options()
        if options:
            self._structure_var.set(options[0])
            self._on_structure_change(options[0])

    def _on_structure_change(self, _value: str) -> None:
        structure_id = self._parse_structure_id(self._structure_var.get())
        if not structure_id:
            return
        explosives = available_explosives_for(structure_id)
        names = [e.name for e in explosives]
        self._explosive_menu.configure(values=names)
        if names:
            self._explosive_var.set(names[0])

    def _on_auto_toggle(self) -> None:
        state = "disabled" if self._auto_var.get() else "normal"
        self._explosive_menu.configure(state=state)

    def _parse_count(self) -> int:
        try:
            value = int(self._count_var.get().strip())
            return max(1, value)
        except ValueError:
            return 1

    def _explosive_id_from_name(self, name: str) -> Optional[str]:
        for explosive in EXPLOSIVE_BY_ID.values():
            if explosive.name == name:
                return explosive.id
        return None

    def _add_entry(self) -> None:
        structure_id = self._parse_structure_id(self._structure_var.get())
        if not structure_id:
            return

        count = self._parse_count()
        explosive_id: Optional[str] = None
        if not self._auto_var.get():
            explosive_id = self._explosive_id_from_name(self._explosive_var.get())

        entry = calculate_entry(structure_id, count, explosive_id)
        if entry:
            self._entries.append(entry)
            self._save()
            self._refresh_table()

    def _remove_entry(self, index: int) -> None:
        if 0 <= index < len(self._entries):
            del self._entries[index]
            self._save()
            self._refresh_table()

    def _clear_entries(self) -> None:
        self._entries.clear()
        self._save()
        self._refresh_table()

    def _refresh_table(self) -> None:
        if not self._table_frame or not self._totals_frame or not self._time_label:
            return

        for widget in self._table_frame.winfo_children():
            widget.destroy()
        for widget in self._totals_frame.winfo_children():
            widget.destroy()

        if not self._entries:
            ctk.CTkLabel(
                self._table_frame,
                text="Список пуст. Добавьте строения для расчёта.",
                text_color="#6b7280",
            ).pack(pady=24)
        else:
            for index, entry in enumerate(self._entries):
                self._render_row(index, entry)

        summary = calculate_raid(self._entries)
        self._time_label.configure(
            text=f"Общее время рейда: {format_duration(summary.total_seconds)}"
        )

        totals = summary.resource_totals()
        if not totals:
            ctk.CTkLabel(
                self._totals_frame,
                text="Нет данных",
                text_color="#6b7280",
            ).pack(anchor="w")
        else:
            grid = ctk.CTkFrame(self._totals_frame, fg_color="transparent")
            grid.pack(fill="x")
            col = 0
            row = 0
            for label, value in totals.items():
                item = ctk.CTkFrame(grid, fg_color="#242b3d", corner_radius=6)
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
                if col >= 4:
                    col = 0
                    row += 1

        self.request_resize()

    def _render_row(self, index: int, entry: RaidEntry) -> None:
        assert self._table_frame is not None
        row = ctk.CTkFrame(self._table_frame, fg_color="#161c2a", corner_radius=4)
        row.pack(fill="x", pady=2)

        structure = entry.structure
        explosive = entry.explosive

        cells = [
            (structure.name, 150),
            (str(entry.structure_count), 50),
            (explosive.name, 150),
            (str(entry.explosive_count), 55),
            (format_duration(entry.raid_seconds), 80),
            (format_cost_short(entry.cost), 220),
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
