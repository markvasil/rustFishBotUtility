from __future__ import annotations

from typing import Dict, Optional

import customtkinter as ctk

from features.base import Feature
from features.electricity.calculator import calculate_electricity
from features.shared_data import BATTERY_CAPACITY, ELECTRICITY_CONSUMERS, ELECTRICITY_SOURCES


class ElectricityFeature(Feature):
    id = "electricity"
    title = "Электрика"

    def __init__(self) -> None:
        super().__init__()
        self._source_vars: Dict[str, ctk.StringVar] = {}
        self._consumer_vars: Dict[str, ctk.StringVar] = {}
        self._battery_vars: Dict[str, ctk.StringVar] = {}
        self._result_frame: Optional[ctk.CTkFrame] = None

    def build(self, parent: ctk.CTkFrame) -> None:
        ctk.CTkLabel(
            parent, text="Источники, потребители и батареи — баланс мощности (rW)",
            font=ctk.CTkFont(size=13), text_color="#a0a8b8",
        ).pack(anchor="w", padx=12, pady=(12, 8))

        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.pack(fill="x", padx=12, pady=(0, 8))

        for title, items, store, color in [
            ("Источники", ELECTRICITY_SOURCES, self._source_vars, "#1e3a4f"),
            ("Потребители", ELECTRICITY_CONSUMERS, self._consumer_vars, "#3d2a1f"),
            ("Батареи", BATTERY_CAPACITY, self._battery_vars, "#2a3142"),
        ]:
            block = ctk.CTkFrame(body, fg_color=color, corner_radius=8)
            block.pack(side="left", fill="both", expand=True, padx=4)
            ctk.CTkLabel(block, text=title, font=ctk.CTkFont(size=12, weight="bold"),
                         text_color="#e8ecf4").pack(anchor="w", padx=8, pady=(8, 4))
            for item_id, (label, _watts) in items.items():
                row = ctk.CTkFrame(block, fg_color="transparent")
                row.pack(fill="x", padx=8, pady=2)
                ctk.CTkLabel(row, text=label, width=140, anchor="w", font=ctk.CTkFont(size=11)).pack(side="left")
                var = ctk.StringVar(value="0")
                store[item_id] = var
                entry = ctk.CTkEntry(row, textvariable=var, width=50)
                entry.pack(side="right")
                var.trace_add("write", lambda *_: self._calculate())

        self._result_frame = ctk.CTkFrame(parent, fg_color="#1a2030", corner_radius=8)
        self._result_frame.pack(fill="x", padx=12, pady=(0, 12))
        self._calculate()

    def _parse_vars(self, store: Dict[str, ctk.StringVar]) -> Dict[str, int]:
        result: Dict[str, int] = {}
        for key, var in store.items():
            try:
                result[key] = max(0, int(var.get().strip()))
            except ValueError:
                result[key] = 0
        return result

    def _calculate(self) -> None:
        if not self._result_frame:
            return
        for w in self._result_frame.winfo_children():
            w.destroy()

        summary = calculate_electricity(
            self._parse_vars(self._source_vars),
            self._parse_vars(self._consumer_vars),
            self._parse_vars(self._battery_vars),
        )

        net_color = "#4ade80" if summary.net >= 0 else "#f87171"
        lines = [
            f"Генерация: {summary.total_generation} rW",
            f"Потребление: {summary.total_consumption} rW",
            f"Баланс: {summary.net:+d} rW",
            f"Ёмкость батарей: {summary.total_battery} rW",
        ]
        for line in lines:
            color = net_color if "Баланс" in line else "#d1d7e3"
            ctk.CTkLabel(self._result_frame, text=line, font=ctk.CTkFont(size=13),
                         text_color=color).pack(anchor="w", padx=12, pady=2)
        ctk.CTkLabel(self._result_frame, text=" ", height=6).pack()
        self.request_resize()
