from __future__ import annotations

from typing import Dict, List, Optional

import customtkinter as ctk

from features.base import Feature
from features.resource_machines.calculator import calculate_machine, format_duration
from features.shared_data import MACHINES


class ResourceMachinesFeature(Feature):
    id = "resource_machines"
    title = "Экскаватор / карьер"

    def __init__(self) -> None:
        super().__init__()
        self._machine_var: Optional[ctk.StringVar] = None
        self._diesel_var: Optional[ctk.StringVar] = None
        self._entries: List[tuple[str, int]] = []
        self._table_frame: Optional[ctk.CTkFrame] = None
        self._result_frame: Optional[ctk.CTkFrame] = None
        self._time_label: Optional[ctk.CTkLabel] = None

    def build(self, parent: ctk.CTkFrame) -> None:
        self._diesel_var = ctk.StringVar(value="10")
        machine_names = [MACHINES[k]["name"] for k in MACHINES]
        self._machine_name_to_id = {MACHINES[k]["name"]: k for k in MACHINES}
        self._machine_var = ctk.StringVar(value=machine_names[0])

        ctk.CTkLabel(
            parent, text="Дизель → время работы → выход ресурсов",
            font=ctk.CTkFont(size=13), text_color="#a0a8b8",
        ).pack(anchor="w", padx=12, pady=(12, 8))

        form = ctk.CTkFrame(parent, fg_color="#1a2030", corner_radius=8)
        form.pack(fill="x", padx=12, pady=(0, 8))
        row = ctk.CTkFrame(form, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=10)
        ctk.CTkOptionMenu(row, variable=self._machine_var, values=machine_names, width=240,
                          fg_color="#2a3142", button_color="#3d4659").pack(side="left", padx=(0, 8))
        ctk.CTkEntry(row, textvariable=self._diesel_var, width=70).pack(side="left")
        ctk.CTkLabel(row, text="дизель").pack(side="left", padx=4)
        ctk.CTkButton(row, text="+ Добавить", width=110, fg_color="#c45c26",
                      command=self._add).pack(side="left", padx=8)
        ctk.CTkButton(row, text="Очистить", width=90, fg_color="#3d4659",
                      command=self._clear).pack(side="left")

        self._table_frame = ctk.CTkFrame(parent, fg_color="#10151f", corner_radius=6)
        self._table_frame.pack(fill="x", padx=12, pady=(0, 8))

        totals = ctk.CTkFrame(parent, fg_color="#1a2030", corner_radius=8)
        totals.pack(fill="x", padx=12, pady=(0, 12))
        ctk.CTkLabel(totals, text="Итого", font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#e8ecf4").pack(anchor="w", padx=12, pady=(10, 2))
        self._time_label = ctk.CTkLabel(totals, text="Время: 0 сек", text_color="#f0b429")
        self._time_label.pack(anchor="w", padx=12, pady=(0, 6))
        self._result_frame = ctk.CTkFrame(totals, fg_color="transparent")
        self._result_frame.pack(fill="x", padx=8, pady=(0, 10))
        self._refresh()

    def _parse_diesel(self) -> int:
        try:
            return max(1, int(self._diesel_var.get().strip()))
        except (ValueError, AttributeError):
            return 1

    def _add(self) -> None:
        mid = self._machine_name_to_id[self._machine_var.get()]
        self._entries.append((mid, self._parse_diesel()))
        self._refresh()

    def _clear(self) -> None:
        self._entries.clear()
        self._refresh()

    def _remove(self, index: int) -> None:
        if 0 <= index < len(self._entries):
            del self._entries[index]
            self._refresh()

    def _refresh(self) -> None:
        if not self._table_frame or not self._result_frame:
            return
        for w in self._table_frame.winfo_children():
            w.destroy()
        for w in self._result_frame.winfo_children():
            w.destroy()

        total_seconds = 0.0
        agg_outputs: Dict[str, int] = {}

        if not self._entries:
            ctk.CTkLabel(self._table_frame, text="Добавьте запуск машины", text_color="#6b7280").pack(pady=16)
        else:
            for i, (mid, diesel) in enumerate(self._entries):
                result = calculate_machine(mid, diesel)
                if not result:
                    continue
                total_seconds += result.seconds
                for k, v in result.outputs.items():
                    agg_outputs[k] = agg_outputs.get(k, 0) + v
                row = ctk.CTkFrame(self._table_frame, fg_color="#161c2a", corner_radius=4)
                row.pack(fill="x", pady=2)
                outs = ", ".join(f"{k}: {v}" for k, v in result.outputs.items())
                ctk.CTkLabel(row, text=f"{result.name} ×{diesel} — {format_duration(result.seconds)} — {outs}",
                             anchor="w", font=ctk.CTkFont(size=11), text_color="#d1d7e3").pack(
                    side="left", padx=8, pady=6)
                ctk.CTkButton(row, text="✕", width=28, height=28, fg_color="#4a2230",
                              command=lambda idx=i: self._remove(idx)).pack(side="right", padx=4)

        if self._time_label:
            self._time_label.configure(text=f"Время: {format_duration(total_seconds)}")
        if agg_outputs:
            grid = ctk.CTkFrame(self._result_frame, fg_color="transparent")
            grid.pack(fill="x")
            col = 0
            for label, value in agg_outputs.items():
                item = ctk.CTkFrame(grid, fg_color="#1e3a4f", corner_radius=6)
                item.grid(row=0, column=col, padx=4, pady=4)
                ctk.CTkLabel(item, text=f"x{value}", font=ctk.CTkFont(size=14, weight="bold"),
                             text_color="#f0b429").pack(padx=10, pady=(6, 0))
                ctk.CTkLabel(item, text=label, font=ctk.CTkFont(size=11),
                             text_color="#9aa3b5").pack(padx=10, pady=(0, 6))
                col += 1
        else:
            ctk.CTkLabel(self._result_frame, text="—", text_color="#6b7280").pack(anchor="w", padx=4)
        self.request_resize()
