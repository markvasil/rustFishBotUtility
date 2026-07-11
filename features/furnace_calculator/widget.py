from __future__ import annotations

from typing import Dict, List, Optional

import customtkinter as ctk

from features.base import Feature
from features.furnace_calculator.calculator import (
    FurnaceInput,
    FurnaceResult,
    calculate_furnace,
    format_duration,
)


class FurnaceCalculatorFeature(Feature):
    id = "furnace_calculator"
    title = "Калькулятор печи"

    def __init__(self) -> None:
        super().__init__()
        self._entries: List[FurnaceInput] = []
        self._metal_var: Optional[ctk.StringVar] = None
        self._sulfur_var: Optional[ctk.StringVar] = None
        self._hqm_var: Optional[ctk.StringVar] = None
        self._charcoal_var: Optional[ctk.StringVar] = None
        self._furnace_count_var: Optional[ctk.StringVar] = None
        self._table_frame: Optional[ctk.CTkFrame] = None
        self._ore_frame: Optional[ctk.CTkFrame] = None
        self._wood_frame: Optional[ctk.CTkFrame] = None
        self._output_frame: Optional[ctk.CTkFrame] = None
        self._time_label: Optional[ctk.CTkLabel] = None

    def build(self, parent: ctk.CTkFrame) -> None:
        self._metal_var = ctk.StringVar(value="0")
        self._sulfur_var = ctk.StringVar(value="0")
        self._hqm_var = ctk.StringVar(value="0")
        self._charcoal_var = ctk.StringVar(value="0")
        self._furnace_count_var = ctk.StringVar(value="1")

        header = ctk.CTkLabel(
            parent,
            text="Сколько руды плавить — калькулятор посчитает дерево, уголь и время",
            font=ctk.CTkFont(size=13),
            text_color="#a0a8b8",
        )
        header.pack(anchor="w", padx=12, pady=(12, 8))

        form = ctk.CTkFrame(parent, fg_color="#1a2030", corner_radius=8)
        form.pack(fill="x", padx=12, pady=(0, 8))

        furnace_row = ctk.CTkFrame(form, fg_color="transparent")
        furnace_row.pack(fill="x", padx=10, pady=(10, 4))
        ctk.CTkLabel(furnace_row, text="Кол-во печей:", width=110, anchor="w").pack(side="left")
        ctk.CTkEntry(
            furnace_row,
            textvariable=self._furnace_count_var,
            width=90,
        ).pack(side="left", padx=(4, 0))
        ctk.CTkLabel(
            furnace_row,
            text="Время делится на число печей, дерево — нет",
            font=ctk.CTkFont(size=11),
            text_color="#6b7280",
        ).pack(side="left", padx=(12, 0))

        self._furnace_count_var.trace_add("write", lambda *_: self._refresh())

        inputs = [
            ("Металл. руда:", self._metal_var),
            ("Серная руда:", self._sulfur_var),
            ("HQM руда:", self._hqm_var),
            ("Нужно угля:", self._charcoal_var),
        ]
        for label, var in inputs:
            row = ctk.CTkFrame(form, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=4)
            ctk.CTkLabel(row, text=label, width=110, anchor="w").pack(side="left")
            ctk.CTkEntry(row, textvariable=var, width=90).pack(side="left", padx=(4, 0))

        buttons = ctk.CTkFrame(form, fg_color="transparent")
        buttons.pack(fill="x", padx=10, pady=(8, 10))

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
            ("Металл", 70),
            ("Сера", 70),
            ("HQM", 70),
            ("Уголь", 70),
            ("Дерево", 80),
            ("Время", 100),
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

        self._table_frame = ctk.CTkFrame(parent, fg_color="#10151f", corner_radius=6)
        self._table_frame.pack(fill="x", padx=12, pady=(0, 8))

        totals = ctk.CTkFrame(parent, fg_color="#1a2030", corner_radius=8)
        totals.pack(fill="x", padx=12, pady=(0, 8))

        ctk.CTkLabel(
            totals,
            text="Итого",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#e8ecf4",
        ).pack(anchor="w", padx=12, pady=(10, 2))

        self._time_label = ctk.CTkLabel(
            totals,
            text="Время плавки: 0 сек",
            font=ctk.CTkFont(size=12),
            text_color="#f0b429",
        )
        self._time_label.pack(anchor="w", padx=12, pady=(0, 6))

        ctk.CTkLabel(
            totals,
            text="Руда для плавки",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#8b93a7",
        ).pack(anchor="w", padx=12, pady=(4, 2))
        self._ore_frame = ctk.CTkFrame(totals, fg_color="transparent")
        self._ore_frame.pack(fill="x", padx=8, pady=(0, 6))

        ctk.CTkLabel(
            totals,
            text="Дерево",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#8b93a7",
        ).pack(anchor="w", padx=12, pady=(4, 2))
        self._wood_frame = ctk.CTkFrame(totals, fg_color="transparent")
        self._wood_frame.pack(fill="x", padx=8, pady=(0, 6))

        ctk.CTkLabel(
            totals,
            text="Результат плавки",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#8b93a7",
        ).pack(anchor="w", padx=12, pady=(4, 2))
        self._output_frame = ctk.CTkFrame(totals, fg_color="transparent")
        self._output_frame.pack(fill="x", padx=8, pady=(0, 10))

        self._refresh()

    def _parse_int(self, var: ctk.StringVar) -> int:
        try:
            return max(0, int(var.get().strip()))
        except ValueError:
            return 0

    def _add_entry(self) -> None:
        inp = FurnaceInput(
            metal_ore=self._parse_int(self._metal_var),
            sulfur_ore=self._parse_int(self._sulfur_var),
            hqm_ore=self._parse_int(self._hqm_var),
            charcoal_needed=self._parse_int(self._charcoal_var),
        )
        if inp.metal_ore or inp.sulfur_ore or inp.hqm_ore or inp.charcoal_needed:
            self._entries.append(inp)
            self._refresh()

    def _remove_entry(self, index: int) -> None:
        if 0 <= index < len(self._entries):
            del self._entries[index]
            self._refresh()

    def _clear_entries(self) -> None:
        self._entries.clear()
        self._refresh()

    def _parse_furnace_count(self) -> int:
        if not self._furnace_count_var:
            return 1
        try:
            return max(1, int(self._furnace_count_var.get().strip()))
        except ValueError:
            return 1

    def _calc(self, inp: FurnaceInput) -> FurnaceResult:
        return calculate_furnace(inp, self._parse_furnace_count())

    def _aggregate(self) -> FurnaceResult:
        combined = FurnaceInput()
        for entry in self._entries:
            combined = combined + entry
        return self._calc(combined)

    def _refresh(self) -> None:
        for frame in (self._table_frame, self._ore_frame, self._wood_frame, self._output_frame):
            if frame:
                for widget in frame.winfo_children():
                    widget.destroy()

        if not self._entries:
            if self._table_frame:
                ctk.CTkLabel(
                    self._table_frame,
                    text="Добавьте руду для расчёта плавки.",
                    text_color="#6b7280",
                ).pack(pady=20)
        else:
            for index, entry in enumerate(self._entries):
                self._render_row(index, self._calc(entry))

        result = self._aggregate()

        if self._time_label:
            count = result.furnace_count
            single = format_duration(result.smelt_seconds_single)
            effective = format_duration(result.smelt_seconds)
            if count > 1:
                text = f"Время плавки ({count} печи): {effective}  (1 печь: {single})"
            else:
                text = f"Время плавки: {effective}"
            self._time_label.configure(text=text)
        if self._ore_frame:
            self._render_grid(self._ore_frame, result.ore_totals(), "#2a3142")
        if self._wood_frame:
            self._render_grid(self._wood_frame, result.smelting_breakdown(), "#3d2a1f")
        if self._output_frame:
            self._render_grid(self._output_frame, result.output_totals(), "#1e3a4f")

        self.request_resize()

    def _render_row(self, index: int, result: FurnaceResult) -> None:
        assert self._table_frame is not None
        row = ctk.CTkFrame(self._table_frame, fg_color="#161c2a", corner_radius=4)
        row.pack(fill="x", pady=2)

        cells = [
            (str(result.metal_ore), 70),
            (str(result.sulfur_ore), 70),
            (str(result.hqm_ore), 70),
            (str(result.charcoal_from_smelting), 70),
            (str(result.total_wood), 80),
            (format_duration(result.smelt_seconds), 100),
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

    def _render_grid(self, parent: ctk.CTkFrame, totals: Dict[str, int], bg_color: str) -> None:
        if not totals:
            ctk.CTkLabel(parent, text="—", text_color="#6b7280").pack(anchor="w", padx=4, pady=4)
            return

        grid = ctk.CTkFrame(parent, fg_color="transparent")
        grid.pack(fill="x")

        col = 0
        for label, value in totals.items():
            item = ctk.CTkFrame(grid, fg_color=bg_color, corner_radius=6)
            item.grid(row=0, column=col, padx=4, pady=4, sticky="ew")
            ctk.CTkLabel(
                item,
                text=f"x{value}",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#f0b429",
            ).pack(padx=10, pady=(6, 0))
            ctk.CTkLabel(
                item,
                text=label,
                font=ctk.CTkFont(size=11),
                text_color="#9aa3b5",
            ).pack(padx=10, pady=(0, 6))
            col += 1
