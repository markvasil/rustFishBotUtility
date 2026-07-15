from __future__ import annotations

import threading
import winsound
from typing import Dict, List, Optional, Set, Tuple

import customtkinter as ctk

from features.base import Feature
from features.genetics.breeding_planner import (
    BreedingPath,
    find_breeding_paths,
    format_gene_profile,
    parse_target_counts,
)
from features.genetics.calculator import calculate_crossbreed, normalize_genes
from features.genetics.calibration import (
    RegionCalibration,
    load_calibrations,
    profile_key,
    save_calibrations,
)
from features.genetics.scan_preview import ScanPreviewWindow
from features.genetics.scanner import SCAN_REGIONS, GeneScanner
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
        self._scan_region_var: Optional[ctk.StringVar] = None
        self._scan_resolution_var: Optional[ctk.StringVar] = None
        self._genes_text: Optional[ctk.CTkTextbox] = None
        self._scan_btn: Optional[ctk.CTkButton] = None
        self._calibrate_btn: Optional[ctk.CTkButton] = None
        self._done_btn: Optional[ctk.CTkButton] = None
        self._scan_preview: Optional[ScanPreviewWindow] = None
        self._calibrating = False
        self._calibrated = False
        self._known_genes: Set[str] = set()
        self._calibration: Dict = {}

        self._center_var: Optional[ctk.StringVar] = None
        self._top_var: Optional[ctk.StringVar] = None
        self._bottom_var: Optional[ctk.StringVar] = None
        self._left_var: Optional[ctk.StringVar] = None
        self._right_var: Optional[ctk.StringVar] = None
        self._result_frame: Optional[ctk.CTkFrame] = None
        self._slots_frame: Optional[ctk.CTkFrame] = None
        self._target_vars: Dict[str, ctk.StringVar] = {}
        self._target_sum_var: Optional[ctk.StringVar] = None
        self._breed_paths_frame: Optional[ctk.CTkScrollableFrame] = None
        self._breed_paths_status: Optional[ctk.StringVar] = None
        self._breed_calc_btn: Optional[ctk.CTkButton] = None
        self._max_breed_steps_var: Optional[ctk.StringVar] = None
        self._breed_calculating = False
        self._breed_calc_token = 0

    def build(self, parent: ctk.CTkFrame) -> None:
        self._root = parent.winfo_toplevel()
        if self._session:
            stored = self._session.get_feature(self.id)
            self._calibration = stored.get("calibration", {})
            if stored.get("calibrated"):
                self._calibrated = True

        ctk.CTkLabel(
            parent,
            text="Сканируйте гены из Rust и считайте кроссбридинг (как на rustbreeder.com)",
            font=ctk.CTkFont(size=13),
            text_color="#a0a8b8",
        ).pack(anchor="w", padx=12, pady=(12, 8))

        self._build_scanner_section(parent)
        self._build_gene_list_section(parent)
        self._build_breeding_planner_section(parent)
        self._build_crossbreed_section(parent)

        self._scan_preview = ScanPreviewWindow(self._root, on_calibration_saved=self._persist_calibrations)
        self._scanner = GeneScanner(
            on_gene_found=self._schedule_gene_found,
            on_status=self._schedule_status,
            get_calibrations=self._current_calibrations,
        )
        self._update_target_sum_label()
        self._calculate()

    def _build_scanner_section(self, parent: ctk.CTkFrame) -> None:
        scan_frame = ctk.CTkFrame(parent, fg_color="#1a2030", corner_radius=8)
        scan_frame.pack(fill="x", padx=12, pady=(0, 8))

        controls = ctk.CTkFrame(scan_frame, fg_color="transparent")
        controls.pack(fill="x", padx=10, pady=(10, 6))

        self._calibrate_btn = ctk.CTkButton(
            controls,
            text="Калибровка",
            width=110,
            fg_color="#374151",
            hover_color="#4b5563",
            command=self._start_calibration,
        )
        self._calibrate_btn.pack(side="left")

        self._done_btn = ctk.CTkButton(
            controls,
            text="Готово",
            width=80,
            fg_color="#2d6a4f",
            hover_color="#40916c",
            command=self._finish_calibration,
        )

        self._scan_btn = ctk.CTkButton(
            controls,
            text="Сканировать",
            width=120,
            fg_color="#1f4d3a",
            hover_color="#2d6a4f",
            state="disabled",
            command=self._toggle_scan,
        )
        self._scan_btn.pack(side="left", padx=(8, 0))

        self._scan_region_var = ctk.StringVar(value="Инвентарь")
        ctk.CTkOptionMenu(
            controls,
            variable=self._scan_region_var,
            values=["Оба", "Грядка", "Инвентарь"],
            width=110,
            command=lambda _v: self._on_scan_settings_changed(),
        ).pack(side="left", padx=(8, 0))

        self._scan_resolution_var = ctk.StringVar(value="2K")
        ctk.CTkOptionMenu(
            controls,
            variable=self._scan_resolution_var,
            values=["Авто", "1080p", "2K"],
            width=90,
            command=lambda _v: self._on_scan_settings_changed(),
        ).pack(side="left", padx=(6, 0))

        ctk.CTkButton(
            controls,
            text="Очистить",
            width=90,
            fg_color="#374151",
            hover_color="#4b5563",
            command=self._clear_genes,
        ).pack(side="right")

        self._scan_status_var = ctk.StringVar(
            value="1) Калибровка → двигайте рамку на гены → Готово  2) Сканировать"
        )
        ctk.CTkLabel(
            scan_frame,
            textvariable=self._scan_status_var,
            font=ctk.CTkFont(size=11),
            text_color="#8b93a7",
            wraplength=560,
            justify="left",
        ).pack(anchor="w", padx=10, pady=(0, 10))

        ctk.CTkLabel(
            scan_frame,
            text="Сначала откройте растение в Rust, затем «Калибровка» → двигайте рамки 1–6 на каждый ген",
            font=ctk.CTkFont(size=10),
            text_color="#6b7280",
        ).pack(anchor="w", padx=10, pady=(0, 10))

        self._update_scan_button_state()

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
            text="(клик → центр, Ctrl+C или кнопка → копировать)",
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
        self._genes_text.bind("<Control-c>", self._copy_genes_selection)
        self._genes_text.bind("<Control-C>", self._copy_genes_selection)

    def _build_breeding_planner_section(self, parent: ctk.CTkFrame) -> None:
        section = ctk.CTkFrame(parent, fg_color="#1a2030", corner_radius=8)
        section.pack(fill="x", padx=12, pady=(0, 8))

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
            text="Укажите цель (сумма = 6), выберите число поколений и нажмите Calculate",
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

        self._breed_calc_btn = ctk.CTkButton(
            calc_row,
            text="Calculate",
            width=140,
            fg_color="#2d6a4f",
            hover_color="#40916c",
            command=self._calculate_breeding_paths,
        )
        self._breed_calc_btn.pack(side="left")

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

    def _finish_breed_calculation(self) -> None:
        self._breed_calculating = False
        if self._breed_calc_btn:
            self._breed_calc_btn.configure(state="normal", text="Calculate")

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
            title = f"Вариант {index}: {path.final} ({path.step_count} скрещ.{chance_label})"
            subtitle = f"Цель: {format_gene_profile(target_counts)}"

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
            for donor in step.crossbreeding:
                if donor in available_genes:
                    donor_lines.append(f"• {donor}")
                else:
                    donor_lines.append(f"• {donor} (вывести на предыдущем шаге)")
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

            ctk.CTkLabel(
                row,
                text=f"Результат: {step.result}",
                font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
                text_color="#6ec1e4",
                anchor="w",
            ).pack(anchor="w", padx=8, pady=(0, 8))
            available_genes.add(step.result)

        ctk.CTkButton(
            card,
            text="Подставить в кроссбридинг",
            width=180,
            height=24,
            fg_color="#374151",
            hover_color="#4b5563",
            command=lambda p=path: self._apply_breeding_path(p),
        ).pack(anchor="w", padx=10, pady=(2, 8))

    def _apply_breeding_path(self, path: BreedingPath) -> None:
        if not path.steps:
            if self._center_var:
                self._center_var.set(path.final)
            self._calculate()
            return

        last = path.steps[-1]
        if self._center_var:
            self._center_var.set(last.center or last.result)
        if self._top_var:
            self._top_var.set(last.top)
        if self._bottom_var:
            self._bottom_var.set(last.bottom)
        if self._left_var:
            self._left_var.set(last.left)
        if self._right_var:
            self._right_var.set(last.right)
        self._calculate()

    def _build_crossbreed_section(self, parent: ctk.CTkFrame) -> None:
        ctk.CTkLabel(
            parent,
            text="Кроссбридинг: центр + 4 соседа (G/Y/H=0.6, W/X=1.0)",
            font=ctk.CTkFont(size=12),
            text_color="#a0a8b8",
        ).pack(anchor="w", padx=12, pady=(0, 6))

        self._center_var = ctk.StringVar(value="GYHWWX")
        self._top_var = ctk.StringVar(value="GGYYXX")
        self._bottom_var = ctk.StringVar(value="GGYYXX")
        self._left_var = ctk.StringVar(value="GGYYXX")
        self._right_var = ctk.StringVar(value="GGYYXX")

        form = ctk.CTkFrame(parent, fg_color="#1a2030", corner_radius=8)
        form.pack(fill="x", padx=12, pady=(0, 8))

        grid = ctk.CTkFrame(form, fg_color="transparent")
        grid.pack(padx=20, pady=12)

        def cell(text: str, var: ctk.StringVar, r: int, c: int) -> None:
            frame = ctk.CTkFrame(grid, fg_color="transparent")
            frame.grid(row=r, column=c, padx=6, pady=4)
            ctk.CTkLabel(frame, text=text, font=ctk.CTkFont(size=11), text_color="#8b93a7").pack()
            ctk.CTkEntry(frame, textvariable=var, width=100).pack()

        cell("Сверху", self._top_var, 0, 1)
        cell("Слева", self._left_var, 1, 0)
        cell("Центр", self._center_var, 1, 1)
        cell("Справа", self._right_var, 1, 2)
        cell("Снизу", self._bottom_var, 2, 1)

        ctk.CTkButton(
            form,
            text="Рассчитать",
            width=140,
            fg_color="#c45c26",
            command=self._calculate,
        ).pack(pady=(0, 10))

        self._result_frame = ctk.CTkFrame(parent, fg_color="#1a2030", corner_radius=8)
        self._result_frame.pack(fill="x", padx=12, pady=(0, 8))
        self._slots_frame = ctk.CTkFrame(parent, fg_color="#10151f", corner_radius=6)
        self._slots_frame.pack(fill="x", padx=12, pady=(0, 12))

    def _active_scan_regions(self) -> List[str]:
        mode = self._scan_region_var.get() if self._scan_region_var else "Инвентарь"
        if mode == "Грядка":
            return ["planter"]
        if mode == "Инвентарь":
            return ["inventory"]
        return ["planter", "inventory"]

    def _scan_settings(self) -> tuple[List[str], str]:
        regions = self._active_scan_regions()
        resolution = self._scan_resolution_var.get() if self._scan_resolution_var else "2K"
        return regions, resolution

    def _current_profile_key(self) -> str:
        _, resolution = self._scan_settings()
        return profile_key(None, resolution)

    def _current_calibrations(self) -> Dict[str, RegionCalibration]:
        regions, resolution = self._scan_settings()
        key = profile_key(None, resolution)
        if self._scan_preview and (self._calibrating or self._scan_preview.is_visible):
            live = self._scan_preview.get_calibrations()
            merged = load_calibrations(self._calibration, key, regions)
            merged.update(live)
            return merged
        return load_calibrations(self._calibration, key, regions)

    def _persist_calibrations(self, calibrations: Dict[str, RegionCalibration]) -> None:
        key = self._current_profile_key()
        save_calibrations(self._calibration, key, calibrations)
        if self._session:
            self._session.update_feature(self.id, calibration=self._calibration, calibrated=True)

    def _update_scan_button_state(self) -> None:
        if not self._scan_btn:
            return
        if self._calibrating:
            self._scan_btn.configure(state="disabled")
            return
        if self._calibrated:
            self._scan_btn.configure(state="normal", fg_color="#2d6a4f")
        else:
            self._scan_btn.configure(state="disabled", fg_color="#1f4d3a")

    def _start_calibration(self) -> None:
        if not self._scan_preview:
            return
        if self._scanner and self._scanner.is_running:
            self._scanner.stop()

        regions, resolution = self._scan_settings()
        key = profile_key(None, resolution)
        calibrations = load_calibrations(self._calibration, key, regions)

        self._calibrating = True
        self._done_btn.pack(side="left", padx=(6, 0), before=self._scan_btn)
        if self._calibrate_btn:
            self._calibrate_btn.configure(fg_color="#2d6a4f")
        self._update_scan_button_state()

        self._scan_preview.show_calibration(regions, resolution, calibrations)
        self._set_status("Рамки 1–6 ловят мышь, остальной экран — клики в Rust. Shift+ЛКМ — сдвинуть все")

    def _finish_calibration(self) -> None:
        if not self._scan_preview:
            return

        calibrations = self._scan_preview.finish_calibration()
        self._persist_calibrations(calibrations)
        self._calibrating = False
        self._calibrated = True
        self._done_btn.pack_forget()
        if self._calibrate_btn:
            self._calibrate_btn.configure(fg_color="#374151")
        self._update_scan_button_state()
        self._set_status("Калибровка сохранена. Теперь нажмите «Сканировать»")

    def _on_scan_settings_changed(self) -> None:
        if self._calibrating:
            self._finish_calibration()
            self._start_calibration()
            return
        if self._scanner and self._scanner.is_running:
            regions, resolution = self._scan_settings()
            self._scanner.stop()
            self._scanner.set_profile(resolution)
            self._scanner.start(regions, profile_id=resolution)
        if self._scan_preview and self._scan_preview.is_visible and not self._calibrating:
            regions, resolution = self._scan_settings()
            calibrations = self._current_calibrations()
            self._scan_preview.show_monitoring(regions, resolution, calibrations)

    def _toggle_scan(self) -> None:
        if not self._scanner or not self._calibrated:
            self._set_status("Сначала выполните калибровку")
            return

        if self._scanner.is_running:
            self._scanner.stop()
            if self._scan_preview:
                self._scan_preview.hide()
            if self._scan_btn:
                self._scan_btn.configure(text="Сканировать", fg_color="#2d6a4f")
        else:
            regions, resolution = self._scan_settings()
            self._scanner.set_profile(resolution)
            self._scanner.start(regions, profile_id=resolution)
            if self._scan_preview:
                self._scan_preview.show_monitoring(regions, resolution, self._current_calibrations())
            if self._scan_btn:
                self._scan_btn.configure(text="Остановить", fg_color="#9b2226")

    def _schedule_gene_found(self, genes: str, region_id: str) -> None:
        if self._root:
            self._root.after(0, lambda: self._on_gene_found(genes, region_id))

    def _schedule_status(self, message: str) -> None:
        if self._root:
            self._root.after(0, lambda: self._set_status(message))

    def _on_gene_found(self, genes: str, region_id: str) -> None:
        normalized = normalize_genes(genes)
        if normalized in self._known_genes:
            return

        self._known_genes.add(normalized)
        if self._genes_text:
            current = self._genes_text.get("1.0", "end").strip()
            prefix = "\n" if current else ""
            self._genes_text.insert("end", f"{prefix}{normalized}")
            self._genes_text.see("end")

        region_label = SCAN_REGIONS[region_id].label if region_id in SCAN_REGIONS else region_id
        self._set_status(f"Найдено: {normalized} ({region_label})")
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
        if not self._genes_text or not self._center_var:
            return
        index = self._genes_text.index(f"@{event.x},{event.y}")
        line_no = index.split(".")[0]
        line = self._genes_text.get(f"{line_no}.0", f"{line_no}.end").strip()
        if not line:
            return
        self._center_var.set(normalize_genes(line))
        self._calculate()

    def _calculate(self) -> None:
        if not self._result_frame or not self._slots_frame:
            return
        for widget in self._result_frame.winfo_children():
            widget.destroy()
        for widget in self._slots_frame.winfo_children():
            widget.destroy()

        result, slots = calculate_crossbreed(
            self._center_var.get() if self._center_var else "",
            self._top_var.get() if self._top_var else "",
            self._bottom_var.get() if self._bottom_var else "",
            self._left_var.get() if self._left_var else "",
            self._right_var.get() if self._right_var else "",
        )
        center = normalize_genes(self._center_var.get() if self._center_var else "")

        ctk.CTkLabel(
            self._result_frame,
            text=f"Результат: {result}",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#6ec1e4",
        ).pack(anchor="w", padx=12, pady=(10, 2))
        ctk.CTkLabel(
            self._result_frame,
            text=f"Было: {center}",
            font=ctk.CTkFont(size=12),
            text_color="#9aa3b5",
        ).pack(anchor="w", padx=12, pady=(0, 10))

        for slot in slots:
            row = ctk.CTkFrame(self._slots_frame, fg_color="#161c2a", corner_radius=4)
            row.pack(fill="x", pady=2)
            changed = "→" if slot.center_gene != slot.result_gene else "="
            text = f"Слот {slot.index}: {slot.center_gene} {changed} {slot.result_gene}  |  {slot.explanation}"
            ctk.CTkLabel(
                row,
                text=text,
                anchor="w",
                font=ctk.CTkFont(size=11),
                text_color="#d1d7e3",
            ).pack(padx=8, pady=5)
        self.request_resize()

    def on_hide(self) -> None:
        if self._scanner and self._scanner.is_running:
            self._scanner.stop()
            if self._scan_btn:
                self._scan_btn.configure(text="Сканировать", fg_color="#2d6a4f")
        if self._scan_preview:
            self._scan_preview.hide()
        self._calibrating = False
        self._done_btn.pack_forget()

    def on_shutdown(self) -> None:
        self._breed_calc_token += 1
        self._breed_calculating = False
        if self._scanner:
            self._scanner.stop()
        if self._scan_preview:
            self._scan_preview.destroy()
