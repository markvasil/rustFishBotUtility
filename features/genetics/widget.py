from __future__ import annotations

import threading
import winsound
from typing import Dict, List, Optional, Set

import customtkinter as ctk

from features.base import Feature
from features.genetics.breeding_planner import (
    BreedingPath,
    find_best_plant,
    find_breeding_paths,
    format_gene_profile,
    gene_counts,
    parse_target_counts,
    _sapling_score,
)
from features.genetics.calculator import normalize_genes
from features.genetics.scanner import GeneScanner
from storage.session import SessionStore


class GeneticsFeature(Feature):
    id = "genetics"
    title = "Генетика"

    def __init__(self, session: Optional[SessionStore] = None) -> None:
        super().__init__()
        self._session = session
        self._root: Optional[ctk.CTk] = None
        self._scanner: Optional[GeneScanner] = None
        self._scan_status_var: Optional[ctk.StringVar] = None
        self._genes_text: Optional[ctk.CTkTextbox] = None
        self._scan_btn: Optional[ctk.CTkButton] = None
        self._known_genes: Set[str] = set()

        self._target_vars: Dict[str, ctk.StringVar] = {}
        self._target_sum_var: Optional[ctk.StringVar] = None
        self._breed_paths_frame: Optional[ctk.CTkScrollableFrame] = None
        self._breed_paths_status: Optional[ctk.StringVar] = None
        self._breed_calc_btn: Optional[ctk.CTkButton] = None
        self._breed_best_btn: Optional[ctk.CTkButton] = None
        self._max_breed_steps_var: Optional[ctk.StringVar] = None
        self._breed_calculating = False
        self._breed_calc_token = 0

    def build(self, parent: ctk.CTkFrame) -> None:
        self._root = parent.winfo_toplevel()

        ctk.CTkLabel(
            parent,
            text="Сканируйте гены кликом ЛКМ в Rust и планируйте выведение (как на rustbreeder.com)",
            font=ctk.CTkFont(size=13),
            text_color="#a0a8b8",
        ).pack(anchor="w", padx=12, pady=(12, 8))

        self._build_scanner_section(parent)
        self._build_gene_list_section(parent)
        self._build_breeding_planner_section(parent)

        self._scanner = GeneScanner(
            on_gene_found=self._schedule_gene_found,
            on_status=self._schedule_status,
        )
        self._update_target_sum_label()

    def _build_scanner_section(self, parent: ctk.CTkFrame) -> None:
        scan_frame = ctk.CTkFrame(parent, fg_color="#1a2030", corner_radius=8)
        scan_frame.pack(fill="x", padx=12, pady=(0, 8))

        controls = ctk.CTkFrame(scan_frame, fg_color="transparent")
        controls.pack(fill="x", padx=10, pady=(10, 6))

        self._scan_btn = ctk.CTkButton(
            controls,
            text="Сканировать",
            width=120,
            fg_color="#2d6a4f",
            hover_color="#40916c",
            command=self._toggle_scan,
        )
        self._scan_btn.pack(side="left")

        ctk.CTkButton(
            controls,
            text="Очистить",
            width=90,
            fg_color="#374151",
            hover_color="#4b5563",
            command=self._clear_genes,
        ).pack(side="right")

        self._scan_status_var = ctk.StringVar(
            value="Нажмите «Сканировать», затем кликайте ЛКМ по генам в Rust"
        )
        ctk.CTkLabel(
            scan_frame,
            textvariable=self._scan_status_var,
            font=ctk.CTkFont(size=11),
            text_color="#8b93a7",
            wraplength=560,
            justify="left",
        ).pack(anchor="w", padx=10, pady=(0, 10))

    def _build_gene_list_section(self, parent: ctk.CTkFrame) -> None:
        list_frame = ctk.CTkFrame(parent, fg_color="#1a2030", corner_radius=8)
        list_frame.pack(fill="x", padx=12, pady=(0, 8))

        header = ctk.CTkFrame(list_frame, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(10, 4))
        ctk.CTkLabel(
            header,
            text="Собранные гены",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#d1d7e3",
        ).pack(side="left")
        ctk.CTkLabel(
            header,
            text="(клик → копировать строку, Ctrl+C или кнопка → всё)",
            font=ctk.CTkFont(size=10),
            text_color="#6b7280",
        ).pack(side="left", padx=(8, 0))
        ctk.CTkButton(
            header,
            text="Копировать",
            width=100,
            height=24,
            fg_color="#374151",
            hover_color="#4b5563",
            command=self._copy_collected_genes,
        ).pack(side="right")

        self._genes_text = ctk.CTkTextbox(list_frame, height=120, font=ctk.CTkFont(family="Consolas", size=13))
        self._genes_text.pack(fill="x", padx=10, pady=(0, 10))
        self._genes_text.bind("<Button-1>", self._on_gene_click)
        self._genes_text.bind("<KeyRelease>", self._sync_known_genes)
        self._genes_text.bind("<Control-KeyPress>", self._on_genes_ctrl_key)

    def _build_breeding_planner_section(self, parent: ctk.CTkFrame) -> None:
        section = ctk.CTkFrame(parent, fg_color="#1a2030", corner_radius=8)
        section.pack(fill="x", padx=12, pady=(0, 12))

        header = ctk.CTkFrame(section, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(10, 4))
        ctk.CTkLabel(
            header,
            text="Выведение гена",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#d1d7e3",
        ).pack(side="left")
        ctk.CTkLabel(
            header,
            text="(как на rustbreeder.com)",
            font=ctk.CTkFont(size=10),
            text_color="#6b7280",
        ).pack(side="left", padx=(8, 0))

        ctk.CTkLabel(
            section,
            text=(
                "Укажите цель (сумма = 6), выберите число поколений и нажмите Calculate. "
                "При шансе <100% смотрите метки 1-й/2-й — сажайте этих доноров первыми по порядку "
                "(как на rustbreeder.com/guide)."
            ),
            font=ctk.CTkFont(size=11),
            text_color="#8b93a7",
            wraplength=560,
            justify="left",
        ).pack(anchor="w", padx=10, pady=(0, 8))

        counts_row = ctk.CTkFrame(section, fg_color="transparent")
        counts_row.pack(fill="x", padx=10, pady=(0, 8))

        defaults = {"G": "0", "Y": "0", "H": "0", "W": "0", "X": "0"}
        for gene in "GYHWX":
            cell = ctk.CTkFrame(counts_row, fg_color="transparent")
            cell.pack(side="left", padx=(0, 10))
            ctk.CTkLabel(
                cell,
                text=gene,
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color="#6ec1e4",
            ).pack()
            var = ctk.StringVar(value=defaults[gene])
            var.trace_add("write", lambda *_args: self._update_target_sum_label())
            self._target_vars[gene] = var
            ctk.CTkEntry(cell, textvariable=var, width=48, justify="center").pack(pady=(2, 0))

        self._target_sum_var = ctk.StringVar(value="Сумма: 0 / 6")
        ctk.CTkLabel(
            counts_row,
            textvariable=self._target_sum_var,
            font=ctk.CTkFont(size=11),
            text_color="#9aa3b5",
        ).pack(side="left", padx=(8, 0))

        calc_row = ctk.CTkFrame(section, fg_color="transparent")
        calc_row.pack(fill="x", padx=10, pady=(0, 6))

        self._breed_best_btn = ctk.CTkButton(
            calc_row,
            text="Найти лучший",
            width=140,
            fg_color="#1f6feb",
            hover_color="#388bfd",
            command=self._calculate_best_plant,
        )
        self._breed_best_btn.pack(side="left")

        self._breed_calc_btn = ctk.CTkButton(
            calc_row,
            text="Calculate",
            width=140,
            fg_color="#2d6a4f",
            hover_color="#40916c",
            command=self._calculate_breeding_paths,
        )
        self._breed_calc_btn.pack(side="left", padx=(8, 0))

        steps_cell = ctk.CTkFrame(calc_row, fg_color="transparent")
        steps_cell.pack(side="left", padx=(12, 0))
        ctk.CTkLabel(
            steps_cell,
            text="Макс. поколений",
            font=ctk.CTkFont(size=11),
            text_color="#9aa3b5",
        ).pack(side="left", padx=(0, 8))
        self._max_breed_steps_var = ctk.StringVar(value="2")
        ctk.CTkOptionMenu(
            steps_cell,
            variable=self._max_breed_steps_var,
            values=["1", "2", "3", "4", "5"],
            width=56,
        ).pack(side="left")

        self._breed_paths_status = ctk.StringVar(
            value="Отсканируйте гены, задайте цель и нажмите Calculate"
        )
        ctk.CTkLabel(
            section,
            textvariable=self._breed_paths_status,
            font=ctk.CTkFont(size=11),
            text_color="#8b93a7",
            wraplength=560,
            justify="left",
        ).pack(anchor="w", padx=10, pady=(0, 8))

        self._breed_paths_frame = ctk.CTkScrollableFrame(
            section,
            fg_color="#10151f",
            corner_radius=6,
            height=260,
        )
        self._breed_paths_frame.pack(fill="x", padx=10, pady=(0, 10))

    def _update_target_sum_label(self) -> None:
        if not self._target_sum_var:
            return
        total = 0
        for gene, var in self._target_vars.items():
            try:
                total += max(0, int(var.get().strip() or "0"))
            except ValueError:
                pass
        color_note = ""
        if total != 6:
            color_note = " — нужно 6"
        self._target_sum_var.set(f"Сумма: {total} / 6{color_note}")

    def _collect_scanned_genes(self) -> List[str]:
        if not self._genes_text:
            return []
        text = self._genes_text.get("1.0", "end")
        return [normalize_genes(line) for line in text.splitlines() if line.strip()]

    def _copy_collected_genes(self) -> None:
        if not self._genes_text or not self._root:
            return
        text = self._genes_text.get("1.0", "end").strip()
        if not text:
            return
        self._root.clipboard_clear()
        self._root.clipboard_append(text)
        self._root.update()

    def _on_genes_ctrl_key(self, event=None) -> Optional[str]:
        keycode = getattr(event, "keycode", None)
        keysym = (getattr(event, "keysym", "") or "").lower()
        if keycode == 86 or keysym in ("v", "cyrillic_em", "м"):
            return self._paste_into_genes(event)
        if keycode == 67 or keysym in ("c", "cyrillic_es", "с"):
            return self._copy_genes_selection(event)
        return None

    def _paste_into_genes(self, _event=None) -> Optional[str]:
        if not self._genes_text or not self._root:
            return "break"
        try:
            clip = self._root.clipboard_get()
        except Exception:
            return "break"
        try:
            self._genes_text.delete("sel.first", "sel.last")
        except Exception:
            pass
        self._genes_text.insert("insert", clip)
        self._sync_known_genes()
        return "break"

    def _copy_genes_selection(self, _event=None) -> Optional[str]:
        if not self._genes_text or not self._root:
            return None
        try:
            selected = self._genes_text.get("sel.first", "sel.last")
        except Exception:
            selected = ""
        if selected.strip():
            self._root.clipboard_clear()
            self._root.clipboard_append(selected.strip())
            self._root.update()
            return "break"
        self._copy_collected_genes()
        return "break"

    def _read_target_counts(self) -> tuple[Dict[str, int], Optional[str]]:
        values: Dict[str, int] = {}
        for gene, var in self._target_vars.items():
            raw = var.get().strip() or "0"
            if not raw.isdigit():
                return values, f"Поле {gene}: введите число от 0 до 6"
            values[gene] = int(raw)
        return parse_target_counts(values)

    def _read_max_breed_steps(self) -> tuple[int, Optional[str]]:
        if not self._max_breed_steps_var:
            return 3, None
        raw = self._max_breed_steps_var.get().strip() or "3"
        if not raw.isdigit():
            return 3, "Макс. поколений: выберите число от 1 до 5"
        value = int(raw)
        if value < 1 or value > 5:
            return 3, "Макс. поколений: от 1 до 5"
        return value, None

    def _calculate_breeding_paths(self) -> None:
        if not self._breed_paths_frame or self._breed_calculating:
            return

        for widget in self._breed_paths_frame.winfo_children():
            widget.destroy()

        available = self._collect_scanned_genes()
        target_counts, error = self._read_target_counts()
        if error:
            if self._breed_paths_status:
                self._breed_paths_status.set(error)
            return

        max_steps, steps_error = self._read_max_breed_steps()
        if steps_error:
            if self._breed_paths_status:
                self._breed_paths_status.set(steps_error)
            return

        self._breed_calculating = True
        self._breed_calc_token += 1
        token = self._breed_calc_token
        gene_count = len({normalize_genes(g) for g in available})

        if self._breed_calc_btn:
            self._breed_calc_btn.configure(state="disabled", text="Считаю...")
        if self._breed_best_btn:
            self._breed_best_btn.configure(state="disabled")
        if self._breed_paths_status:
            self._breed_paths_status.set(
                f"Ищем пути ({gene_count} генов, до {max_steps} покол.)…"
            )

        def worker() -> None:
            paths, search_error = find_breeding_paths(
                available,
                target_counts,
                max_steps=max_steps,
                max_paths=6,
            )
            if self._root:
                self._root.after(
                    0,
                    lambda: self._apply_breeding_paths_result(
                        token,
                        paths,
                        search_error,
                        target_counts,
                    ),
                )

        threading.Thread(target=worker, daemon=True, name="BreedPlanner").start()

    def _calculate_best_plant(self) -> None:
        if not self._breed_paths_frame or self._breed_calculating:
            return

        for widget in self._breed_paths_frame.winfo_children():
            widget.destroy()

        available = self._collect_scanned_genes()
        if not available:
            if self._breed_paths_status:
                self._breed_paths_status.set("Сначала отсканируйте или введите гены")
            return

        max_steps, steps_error = self._read_max_breed_steps()
        if steps_error:
            if self._breed_paths_status:
                self._breed_paths_status.set(steps_error)
            return

        self._breed_calculating = True
        self._breed_calc_token += 1
        token = self._breed_calc_token
        gene_count = len({normalize_genes(g) for g in available})

        if self._breed_best_btn:
            self._breed_best_btn.configure(state="disabled", text="Ищу...")
        if self._breed_calc_btn:
            self._breed_calc_btn.configure(state="disabled")
        if self._breed_paths_status:
            self._breed_paths_status.set(
                f"Ищу лучший ген из {gene_count} клонов (до {max_steps} покол.)…"
            )

        def worker() -> None:
            paths, search_error = find_best_plant(
                available,
                max_steps=max_steps,
                max_paths=3,
            )
            if self._root:
                self._root.after(
                    0,
                    lambda: self._apply_best_plant_result(token, paths, search_error),
                )

        threading.Thread(target=worker, daemon=True, name="BreedBest").start()

    def _apply_best_plant_result(
        self,
        token: int,
        paths: List[BreedingPath],
        search_error: Optional[str],
    ) -> None:
        if token != self._breed_calc_token or not self._breed_paths_frame:
            return

        self._finish_breed_calculation()

        for widget in self._breed_paths_frame.winfo_children():
            widget.destroy()

        if search_error or not paths:
            message = search_error or "Ничего не удалось вывести из этих генов"
            if self._breed_paths_status:
                self._breed_paths_status.set(message)
            ctk.CTkLabel(
                self._breed_paths_frame,
                text=message,
                font=ctk.CTkFont(size=11),
                text_color="#f4a261",
                wraplength=540,
                justify="left",
            ).pack(anchor="w", padx=8, pady=8)
            self.request_resize()
            return

        best = paths[0]
        genes_label = ", ".join(path.final for path in paths)
        if self._breed_paths_status:
            self._breed_paths_status.set(
                f"Лучшие гены (score {_sapling_score(best.final):g}): {genes_label}"
            )
        for index, path in enumerate(paths, start=1):
            self._render_breeding_path(index, path, gene_counts(path.final))
        self.request_resize()

    def _finish_breed_calculation(self) -> None:
        self._breed_calculating = False
        if self._breed_calc_btn:
            self._breed_calc_btn.configure(state="normal", text="Calculate")
        if self._breed_best_btn:
            self._breed_best_btn.configure(state="normal", text="Найти лучший")

    def _apply_breeding_paths_result(
        self,
        token: int,
        paths: List[BreedingPath],
        search_error: Optional[str],
        target_counts: Dict[str, int],
    ) -> None:
        if token != self._breed_calc_token or not self._breed_paths_frame:
            return

        self._finish_breed_calculation()
        target_label = format_gene_profile(target_counts)

        for widget in self._breed_paths_frame.winfo_children():
            widget.destroy()

        if search_error:
            if self._breed_paths_status:
                self._breed_paths_status.set(search_error)
            ctk.CTkLabel(
                self._breed_paths_frame,
                text=search_error,
                font=ctk.CTkFont(size=11),
                text_color="#f4a261",
                wraplength=540,
                justify="left",
            ).pack(anchor="w", padx=8, pady=8)
            self.request_resize()
            return

        if self._breed_paths_status:
            self._breed_paths_status.set(
                f"Найдено вариантов: {len(paths)} для цели {target_label}"
            )

        for index, path in enumerate(paths, start=1):
            self._render_breeding_path(index, path, target_counts)

        self.request_resize()

    def _render_breeding_path(
        self,
        index: int,
        path: BreedingPath,
        target_counts: Dict[str, int],
    ) -> None:
        if not self._breed_paths_frame:
            return

        card = ctk.CTkFrame(self._breed_paths_frame, fg_color="#161c2a", corner_radius=6)
        card.pack(fill="x", padx=4, pady=4)

        if path.step_count == 0:
            title = f"Вариант {index}: уже есть {path.final}"
            subtitle = format_gene_profile(target_counts)
        else:
            chance_label = f", {path.chance * 100:.0f}%" if path.chance < 0.9999 else ", 100%"
            profile = format_gene_profile(target_counts)
            title = (
                f"Вариант {index}: {path.final} · {profile} "
                f"({path.step_count} скрещ.{chance_label})"
            )
            final_step = path.steps[-1]
            center = final_step.center or "без центра"
            donors = " + ".join(final_step.crossbreeding)
            subtitle = f"Финал: центр {center}, доноры {donors}"

        ctk.CTkLabel(
            card,
            text=title,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#6ec1e4",
            anchor="w",
        ).pack(anchor="w", padx=10, pady=(8, 0))
        ctk.CTkLabel(
            card,
            text=subtitle,
            font=ctk.CTkFont(size=10),
            text_color="#8b93a7",
            anchor="w",
        ).pack(anchor="w", padx=10, pady=(0, 6))

        if not path.steps:
            ctk.CTkLabel(
                card,
                text="Этот ген уже есть среди отсканированных — скрещивание не нужно.",
                font=ctk.CTkFont(size=10),
                text_color="#9aa3b5",
                anchor="w",
                wraplength=540,
                justify="left",
            ).pack(anchor="w", padx=10, pady=(0, 8))
            return

        available_genes = set(self._collect_scanned_genes())
        for step_index, step in enumerate(path.steps, start=1):
            row = ctk.CTkFrame(card, fg_color="#10151f", corner_radius=4)
            row.pack(fill="x", padx=8, pady=(0, 4))

            ctk.CTkLabel(
                row,
                text=f"Шаг {step_index}",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color="#9aa3b5",
                anchor="w",
            ).pack(anchor="w", padx=8, pady=(6, 2))

            donor_lines: List[str] = []
            for donor_index, donor in enumerate(step.crossbreeding):
                order = (
                    step.planting_order[donor_index]
                    if donor_index < len(step.planting_order)
                    else None
                )
                order_note = f" · {order}-й" if order is not None else ""
                if donor in available_genes:
                    donor_lines.append(f"• {donor}{order_note}")
                else:
                    donor_lines.append(f"• {donor}{order_note} (вывести на предыдущем шаге)")
            ctk.CTkLabel(
                row,
                text="Доноры:\n" + "\n".join(donor_lines),
                font=ctk.CTkFont(family="Consolas", size=10),
                text_color="#d1d7e3",
                anchor="w",
                justify="left",
            ).pack(anchor="w", padx=8, pady=(0, 2))

            center_note = step.center if step.center else "любой клон"
            if step.center and step.center not in available_genes:
                center_note = f"{step.center} (вывести на предыдущем шаге)"
            ctk.CTkLabel(
                row,
                text=f"Центр: {center_note}",
                font=ctk.CTkFont(size=10),
                text_color="#b8c0d0",
                anchor="w",
            ).pack(anchor="w", padx=8, pady=(0, 2))

            chance_note = f"{step.chance * 100:.0f}%"
            ctk.CTkLabel(
                row,
                text=f"Шанс: {chance_note}",
                font=ctk.CTkFont(size=10),
                text_color="#b8c0d0",
                anchor="w",
            ).pack(anchor="w", padx=8, pady=(0, 2))

            if step.has_planting_order:
                ordered = [
                    f"{order}-й {donor}"
                    for donor, order in zip(step.crossbreeding, step.planting_order)
                    if order is not None
                ]
                ctk.CTkLabel(
                    row,
                    text=(
                        "Порядок посадки (гайд): сначала "
                        + ", затем ".join(ordered)
                        + ", потом остальные. Слот не важен — важен только порядок."
                    ),
                    font=ctk.CTkFont(size=10),
                    text_color="#f4a261",
                    anchor="w",
                    wraplength=520,
                    justify="left",
                ).pack(anchor="w", padx=8, pady=(0, 2))

            ctk.CTkLabel(
                row,
                text=f"Результат: {step.result}",
                font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
                text_color="#6ec1e4",
                anchor="w",
            ).pack(anchor="w", padx=8, pady=(0, 8))
            available_genes.add(step.result)

    def _toggle_scan(self) -> None:
        if not self._scanner:
            return

        if self._scanner.is_running:
            if self._scan_btn:
                self._scan_btn.configure(state="disabled", text="Останавливаем…")

            def on_stopped() -> None:
                if self._root:
                    self._root.after(0, _finish_stop)

            def _finish_stop() -> None:
                if self._scan_btn:
                    self._scan_btn.configure(state="normal", text="Сканировать", fg_color="#2d6a4f")
                self.request_resize()

            self._scanner.stop_async(on_stopped)
        else:
            self._set_status("Кликните ЛКМ по гену в Rust")
            self._scanner.start()
            if self._scan_btn and self._scanner.is_running:
                self._scan_btn.configure(text="Остановить", fg_color="#9b2226")
            elif self._scan_btn:
                self._scan_btn.configure(text="Сканировать", fg_color="#2d6a4f")

    def _schedule_gene_found(self, genes: str, region_id: str) -> None:
        if self._root:
            self._root.after(0, lambda: self._on_gene_found(genes, region_id))

    def _schedule_status(self, message: str) -> None:
        if self._root:
            self._root.after(0, lambda: self._set_status(message))

    def _on_gene_found(self, genes: str, _region_id: str) -> None:
        normalized = normalize_genes(genes)
        if normalized in self._known_genes:
            self._set_status(f"Уже есть: {normalized}. Кликните следующий ген")
            return

        self._known_genes.add(normalized)
        if self._genes_text:
            current = self._genes_text.get("1.0", "end").strip()
            prefix = "\n" if current else ""
            self._genes_text.insert("end", f"{prefix}{normalized}")
            self._genes_text.see("end")

        self._set_status(f"Найдено: {normalized}. Кликните следующий ген")
        try:
            winsound.Beep(880, 120)
        except OSError:
            pass
        self.request_resize()

    def _set_status(self, message: str) -> None:
        if self._scan_status_var:
            self._scan_status_var.set(message)

    def _clear_genes(self) -> None:
        self._known_genes.clear()
        if self._genes_text:
            self._genes_text.delete("1.0", "end")
        if self._breed_paths_frame:
            for widget in self._breed_paths_frame.winfo_children():
                widget.destroy()
        if self._breed_paths_status:
            self._breed_paths_status.set("Отсканируйте гены, задайте цель и нажмите Calculate")
        self._set_status("Список генов очищен")
        self.request_resize()

    def _sync_known_genes(self, _event=None) -> None:
        if not self._genes_text:
            return
        text = self._genes_text.get("1.0", "end")
        self._known_genes = {
            normalize_genes(line)
            for line in text.splitlines()
            if line.strip()
        }

    def _on_gene_click(self, event) -> None:
        if not self._genes_text or not self._root:
            return
        index = self._genes_text.index(f"@{event.x},{event.y}")
        line_no = index.split(".")[0]
        line = self._genes_text.get(f"{line_no}.0", f"{line_no}.end").strip()
        if not line:
            return
        self._root.clipboard_clear()
        self._root.clipboard_append(normalize_genes(line))
        self._root.update()
        self._set_status(f"Скопировано: {normalize_genes(line)}")

    def on_hide(self) -> None:
        if self._scanner and self._scanner.is_running:
            self._scanner.stop()
            if self._scan_btn:
                self._scan_btn.configure(text="Сканировать", fg_color="#2d6a4f")

    def on_shutdown(self) -> None:
        self._breed_calc_token += 1
        self._breed_calculating = False
        if self._scanner:
            self._scanner.stop()
