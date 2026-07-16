from __future__ import annotations

from typing import Dict, List, Optional, Tuple

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
        self._battery_vars: Dict[str, ctk.StringVar] = {}
        self._consumer_entries: List[Tuple[str, ctk.StringVar]] = []
        self._consumer_pick_var: Optional[ctk.StringVar] = None
        self._consumer_count_var: Optional[ctk.StringVar] = None
        self._consumer_list_frame: Optional[ctk.CTkFrame] = None
        self._result_frame: Optional[ctk.CTkFrame] = None
        self._label_to_consumer_id = {
            label: cid for cid, (label, _watts) in ELECTRICITY_CONSUMERS.items()
        }

    def build(self, parent: ctk.CTkFrame) -> None:
        ctk.CTkLabel(
            parent,
            text="Источники, потребители и аккумуляторы — баланс мощности (rW)",
            font=ctk.CTkFont(size=13),
            text_color="#a0a8b8",
        ).pack(anchor="w", padx=12, pady=(12, 8))

        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(0, 8))

        self._build_fixed_block(
            top,
            "Источники",
            ELECTRICITY_SOURCES,
            self._source_vars,
            "#1e3a4f",
        )
        self._build_fixed_block(
            top,
            "Аккумуляторы",
            BATTERY_CAPACITY,
            self._battery_vars,
            "#2a3142",
        )

        self._build_consumers_block(parent)

        self._result_frame = ctk.CTkFrame(parent, fg_color="#1a2030", corner_radius=8)
        self._result_frame.pack(fill="x", padx=12, pady=(0, 12))
        self._calculate()

    def _build_fixed_block(
        self,
        parent: ctk.CTkFrame,
        title: str,
        items: Dict[str, Tuple[str, int]],
        store: Dict[str, ctk.StringVar],
        color: str,
    ) -> None:
        block = ctk.CTkFrame(parent, fg_color=color, corner_radius=8)
        block.pack(side="left", fill="both", expand=True, padx=4)
        ctk.CTkLabel(
            block,
            text=title,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#e8ecf4",
        ).pack(anchor="w", padx=8, pady=(8, 4))
        for item_id, (label, _watts) in items.items():
            row = ctk.CTkFrame(block, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=2)
            ctk.CTkLabel(
                row, text=label, width=160, anchor="w", font=ctk.CTkFont(size=11),
            ).pack(side="left")
            var = ctk.StringVar(value="0")
            store[item_id] = var
            ctk.CTkEntry(row, textvariable=var, width=50).pack(side="right")
            var.trace_add("write", lambda *_: self._calculate())

    def _build_consumers_block(self, parent: ctk.CTkFrame) -> None:
        block = ctk.CTkFrame(parent, fg_color="#3d2a1f", corner_radius=8)
        block.pack(fill="x", padx=12, pady=(0, 8))

        ctk.CTkLabel(
            block,
            text="Потребители",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#e8ecf4",
        ).pack(anchor="w", padx=10, pady=(8, 4))

        form = ctk.CTkFrame(block, fg_color="transparent")
        form.pack(fill="x", padx=10, pady=(0, 6))

        labels = sorted(self._label_to_consumer_id.keys())
        self._consumer_pick_var = ctk.StringVar(value=labels[0] if labels else "")
        self._consumer_count_var = ctk.StringVar(value="1")

        ctk.CTkOptionMenu(
            form,
            variable=self._consumer_pick_var,
            values=labels or [""],
            width=260,
            fg_color="#2a3142",
            button_color="#3d4659",
        ).pack(side="left", padx=(0, 8))

        ctk.CTkEntry(form, textvariable=self._consumer_count_var, width=56).pack(
            side="left", padx=(0, 8),
        )
        ctk.CTkButton(
            form,
            text="+ Добавить",
            width=110,
            fg_color="#c45c26",
            hover_color="#a04a1e",
            command=self._add_consumer,
        ).pack(side="left")

        self._consumer_list_frame = ctk.CTkFrame(block, fg_color="transparent")
        self._consumer_list_frame.pack(fill="x", padx=8, pady=(0, 8))
        self._refresh_consumer_list()

    def _parse_count(self, raw: str) -> int:
        try:
            return max(0, int(raw.strip()))
        except ValueError:
            return 0

    def _add_consumer(self) -> None:
        if not self._consumer_pick_var or not self._consumer_count_var:
            return
        label = self._consumer_pick_var.get()
        consumer_id = self._label_to_consumer_id.get(label)
        if not consumer_id:
            return
        count = self._parse_count(self._consumer_count_var.get())
        if count <= 0:
            return

        for existing_id, var in self._consumer_entries:
            if existing_id == consumer_id:
                var.set(str(self._parse_count(var.get()) + count))
                self._calculate()
                return

        var = ctk.StringVar(value=str(count))
        var.trace_add("write", lambda *_: self._calculate())
        self._consumer_entries.append((consumer_id, var))
        self._refresh_consumer_list()
        self._calculate()

    def _remove_consumer(self, index: int) -> None:
        if 0 <= index < len(self._consumer_entries):
            del self._consumer_entries[index]
            self._refresh_consumer_list()
            self._calculate()

    def _refresh_consumer_list(self) -> None:
        if not self._consumer_list_frame:
            return
        for widget in self._consumer_list_frame.winfo_children():
            widget.destroy()

        if not self._consumer_entries:
            ctk.CTkLabel(
                self._consumer_list_frame,
                text="Список пуст. Добавьте потребителей из списка выше.",
                text_color="#9aa3b5",
                font=ctk.CTkFont(size=11),
            ).pack(anchor="w", padx=4, pady=6)
            self.request_resize()
            return

        for index, (consumer_id, var) in enumerate(self._consumer_entries):
            label, watts = ELECTRICITY_CONSUMERS[consumer_id]
            row = ctk.CTkFrame(self._consumer_list_frame, fg_color="#2a1f18", corner_radius=6)
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(
                row,
                text=f"{label}  ({watts} rW)",
                anchor="w",
                font=ctk.CTkFont(size=11),
            ).pack(side="left", padx=8, pady=6)
            ctk.CTkEntry(row, textvariable=var, width=50).pack(side="right", padx=(0, 4))
            ctk.CTkButton(
                row,
                text="✕",
                width=28,
                height=28,
                fg_color="#4a2230",
                hover_color="#6a2f42",
                command=lambda i=index: self._remove_consumer(i),
            ).pack(side="right", padx=4)

        self.request_resize()

    def _parse_vars(self, store: Dict[str, ctk.StringVar]) -> Dict[str, int]:
        result: Dict[str, int] = {}
        for key, var in store.items():
            result[key] = self._parse_count(var.get())
        return result

    def _consumer_counts(self) -> Dict[str, int]:
        result: Dict[str, int] = {}
        for consumer_id, var in self._consumer_entries:
            result[consumer_id] = result.get(consumer_id, 0) + self._parse_count(var.get())
        return result

    def _calculate(self) -> None:
        if not self._result_frame:
            return
        for w in self._result_frame.winfo_children():
            w.destroy()

        summary = calculate_electricity(
            self._parse_vars(self._source_vars),
            self._consumer_counts(),
            self._parse_vars(self._battery_vars),
        )

        net_color = "#4ade80" if summary.net >= 0 else "#f87171"
        lines = [
            f"Генерация: {summary.total_generation} rW",
            f"Потребление: {summary.total_consumption} rW",
            f"Баланс: {summary.net:+d} rW",
            f"Ёмкость аккумуляторов: {summary.total_battery} rWm",
        ]
        for line in lines:
            color = net_color if "Баланс" in line else "#d1d7e3"
            ctk.CTkLabel(
                self._result_frame,
                text=line,
                font=ctk.CTkFont(size=13),
                text_color=color,
            ).pack(anchor="w", padx=12, pady=2)
        ctk.CTkLabel(self._result_frame, text=" ", height=6).pack()
        self.request_resize()
