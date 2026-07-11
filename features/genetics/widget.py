from __future__ import annotations

from typing import Optional

import customtkinter as ctk

from features.base import Feature
from features.genetics.calculator import calculate_crossbreed, normalize_genes


class GeneticsFeature(Feature):
    id = "genetics"
    title = "Генетика"

    def __init__(self) -> None:
        super().__init__()
        self._center_var: Optional[ctk.StringVar] = None
        self._top_var: Optional[ctk.StringVar] = None
        self._bottom_var: Optional[ctk.StringVar] = None
        self._left_var: Optional[ctk.StringVar] = None
        self._right_var: Optional[ctk.StringVar] = None
        self._result_frame: Optional[ctk.CTkFrame] = None
        self._slots_frame: Optional[ctk.CTkFrame] = None

    def build(self, parent: ctk.CTkFrame) -> None:
        self._center_var = ctk.StringVar(value="GYHWWX")
        self._top_var = ctk.StringVar(value="GGYYXX")
        self._bottom_var = ctk.StringVar(value="GGYYXX")
        self._left_var = ctk.StringVar(value="GGYYXX")
        self._right_var = ctk.StringVar(value="GGYYXX")

        ctk.CTkLabel(
            parent, text="Кроссбридинг: центр + 4 соседа (G/Y/H=0.6, W/X=1.0)",
            font=ctk.CTkFont(size=13), text_color="#a0a8b8",
        ).pack(anchor="w", padx=12, pady=(12, 8))

        form = ctk.CTkFrame(parent, fg_color="#1a2030", corner_radius=8)
        form.pack(fill="x", padx=12, pady=(0, 8))

        grid = ctk.CTkFrame(form, fg_color="transparent")
        grid.pack(padx=20, pady=12)

        def cell(text: str, var: ctk.StringVar, r: int, c: int) -> None:
            f = ctk.CTkFrame(grid, fg_color="transparent")
            f.grid(row=r, column=c, padx=6, pady=4)
            ctk.CTkLabel(f, text=text, font=ctk.CTkFont(size=11), text_color="#8b93a7").pack()
            ctk.CTkEntry(f, textvariable=var, width=100).pack()

        cell("Сверху", self._top_var, 0, 1)
        cell("Слева", self._left_var, 1, 0)
        cell("Центр", self._center_var, 1, 1)
        cell("Справа", self._right_var, 1, 2)
        cell("Снизу", self._bottom_var, 2, 1)

        ctk.CTkButton(form, text="Рассчитать", width=140, fg_color="#c45c26",
                      command=self._calculate).pack(pady=(0, 10))

        self._result_frame = ctk.CTkFrame(parent, fg_color="#1a2030", corner_radius=8)
        self._result_frame.pack(fill="x", padx=12, pady=(0, 8))
        self._slots_frame = ctk.CTkFrame(parent, fg_color="#10151f", corner_radius=6)
        self._slots_frame.pack(fill="x", padx=12, pady=(0, 12))
        self._calculate()

    def _calculate(self) -> None:
        if not self._result_frame or not self._slots_frame:
            return
        for w in self._result_frame.winfo_children():
            w.destroy()
        for w in self._slots_frame.winfo_children():
            w.destroy()

        result, slots = calculate_crossbreed(
            self._center_var.get() if self._center_var else "",
            self._top_var.get() if self._top_var else "",
            self._bottom_var.get() if self._bottom_var else "",
            self._left_var.get() if self._left_var else "",
            self._right_var.get() if self._right_var else "",
        )
        center = normalize_genes(self._center_var.get() if self._center_var else "")

        ctk.CTkLabel(self._result_frame, text=f"Результат: {result}", font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#6ec1e4").pack(anchor="w", padx=12, pady=(10, 2))
        ctk.CTkLabel(self._result_frame, text=f"Было: {center}", font=ctk.CTkFont(size=12),
                     text_color="#9aa3b5").pack(anchor="w", padx=12, pady=(0, 10))

        for slot in slots:
            row = ctk.CTkFrame(self._slots_frame, fg_color="#161c2a", corner_radius=4)
            row.pack(fill="x", pady=2)
            changed = "→" if slot.center_gene != slot.result_gene else "="
            text = f"Слот {slot.index}: {slot.center_gene} {changed} {slot.result_gene}  |  {slot.explanation}"
            ctk.CTkLabel(row, text=text, anchor="w", font=ctk.CTkFont(size=11),
                         text_color="#d1d7e3").pack(padx=8, pady=5)
        self.request_resize()
