from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

import customtkinter as ctk
import keyboard

from features.base import Feature
from features.click_scripts.engine import ScriptEngine
from features.click_scripts.models import (
    HOLD_KEY_LABELS,
    HOLD_KEY_VALUES,
    HOLD_KEYS,
    MOUSE_BUTTON_LABELS,
    MOUSE_BUTTONS,
    ClickScript,
    ScriptStep,
)
from features.click_scripts.picker import PointPicker
from storage.session import SessionStore

if TYPE_CHECKING:
    from overlay.window import OverlayWindow


class ClickScriptsFeature(Feature):
    id = "click_scripts"
    title = "Скрипты"

    def __init__(self, session: SessionStore, overlay: OverlayWindow) -> None:
        super().__init__()
        self._session = session
        self._overlay = overlay
        self._scripts: List[ClickScript] = []
        self._selected_id: Optional[str] = None
        self._hotkey_handles: List[object] = []
        self._pick_step_index: Optional[int] = None

        self._scripts_frame: Optional[ctk.CTkFrame] = None
        self._editor_frame: Optional[ctk.CTkFrame] = None
        self._steps_frame: Optional[ctk.CTkFrame] = None
        self._status_var = ctk.StringVar(value="Готово")
        self._name_var = ctk.StringVar(value="")
        self._hotkey_var = ctk.StringVar(value="")
        self._loop_var = ctk.BooleanVar(value=False)

        self._picker = PointPicker(overlay.root)
        self._engine = ScriptEngine(
            on_status=self._on_engine_status,
            on_finished=self._on_engine_finished,
        )
        self._load()

    def _load(self) -> None:
        data = self._session.get_feature(self.id)
        self._scripts = [
            ClickScript.from_dict(item)
            for item in data.get("scripts", [])
            if isinstance(item, dict)
        ]
        self._selected_id = data.get("selected_id")
        if self._selected_id and not any(s.id == self._selected_id for s in self._scripts):
            self._selected_id = None
        if self._selected_id is None and self._scripts:
            self._selected_id = self._scripts[0].id

    def _save(self) -> None:
        self._session.set_feature(
            self.id,
            {
                "scripts": [s.to_dict() for s in self._scripts],
                "selected_id": self._selected_id,
            },
        )

    def _selected(self) -> Optional[ClickScript]:
        for script in self._scripts:
            if script.id == self._selected_id:
                return script
        return None

    def build(self, parent: ctk.CTkFrame) -> None:
        ctk.CTkLabel(
            parent,
            text="Автоклики по координатам: шаги, задержки, удержание клавиши",
            font=ctk.CTkFont(size=13),
            text_color="#a0a8b8",
        ).pack(anchor="w", padx=12, pady=(12, 8))

        toolbar = ctk.CTkFrame(parent, fg_color="#1a2030", corner_radius=8)
        toolbar.pack(fill="x", padx=12, pady=(0, 6))
        row = ctk.CTkFrame(toolbar, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=8)
        ctk.CTkButton(
            row, text="+ Скрипт", width=90, height=28,
            fg_color="#c45c26", hover_color="#a04a1e", command=self._add_script,
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            row, text="▶ Старт", width=80, height=28,
            fg_color="#2d6a4f", hover_color="#1b4332", command=self._start_selected,
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            row, text="■ Стоп", width=70, height=28,
            fg_color="#4a2230", hover_color="#6a2f42", command=self._stop_engine,
        ).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(
            row, textvariable=self._status_var, text_color="#8b93a7",
            font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=8)

        self._scripts_frame = ctk.CTkFrame(parent, fg_color="#10151f", corner_radius=6)
        self._scripts_frame.pack(fill="x", padx=12, pady=(0, 6))

        self._editor_frame = ctk.CTkFrame(parent, fg_color="#1a2030", corner_radius=8)
        self._editor_frame.pack(fill="x", padx=12, pady=(0, 12))

        self._reload_hotkeys()
        self._refresh_all()

    def on_shutdown(self) -> None:
        self._engine.stop()
        self._picker.cancel()
        self._unload_hotkeys()

    # --- scripts list ---

    def _add_script(self) -> None:
        script = ClickScript(
            name=f"Скрипт {len(self._scripts) + 1}",
            steps=[
                ScriptStep(kind="click", x=960, y=540, interval_ms=200, click_count=5),
            ],
        )
        self._scripts.append(script)
        self._selected_id = script.id
        self._save()
        self._reload_hotkeys()
        self._refresh_all()

    def _delete_script(self, script_id: str) -> None:
        if self._engine.running_script_id == script_id:
            self._engine.stop()
        self._scripts = [s for s in self._scripts if s.id != script_id]
        if self._selected_id == script_id:
            self._selected_id = self._scripts[0].id if self._scripts else None
        self._save()
        self._reload_hotkeys()
        self._refresh_all()

    def _select_script(self, script_id: str) -> None:
        self._apply_editor_to_selected()
        self._selected_id = script_id
        self._save()
        self._refresh_all()

    def _refresh_scripts_list(self) -> None:
        if not self._scripts_frame:
            return
        for w in self._scripts_frame.winfo_children():
            w.destroy()
        if not self._scripts:
            ctk.CTkLabel(
                self._scripts_frame,
                text="Нет скриптов. Создайте первый.",
                text_color="#6b7280",
            ).pack(pady=14)
            return
        for script in self._scripts:
            active = script.id == self._selected_id
            running = self._engine.running_script_id == script.id
            row = ctk.CTkFrame(
                self._scripts_frame,
                fg_color="#2a3142" if active else "#161c2a",
                corner_radius=4,
                border_width=1 if active else 0,
                border_color="#e07a3a",
            )
            row.pack(fill="x", padx=4, pady=2)
            mark = "● " if running else ""
            label = f"{mark}{script.name}"
            if script.hotkey:
                label += f"  [{script.hotkey}]"
            label += f"  · {len(script.steps)} шаг."
            ctk.CTkButton(
                row, text=label, anchor="w", height=28,
                fg_color="transparent", hover_color="#3d4659",
                command=lambda sid=script.id: self._select_script(sid),
            ).pack(side="left", fill="x", expand=True, padx=4, pady=2)
            ctk.CTkButton(
                row, text="✕", width=28, height=28,
                fg_color="#4a2230", hover_color="#6a2f42",
                command=lambda sid=script.id: self._delete_script(sid),
            ).pack(side="right", padx=4, pady=2)

    # --- editor ---

    def _refresh_editor(self) -> None:
        if not self._editor_frame:
            return
        for w in self._editor_frame.winfo_children():
            w.destroy()
        script = self._selected()
        if script is None:
            ctk.CTkLabel(
                self._editor_frame,
                text="Выберите или создайте скрипт",
                text_color="#6b7280",
            ).pack(pady=20)
            self._steps_frame = None
            return

        self._name_var.set(script.name)
        self._hotkey_var.set(script.hotkey)
        self._loop_var.set(script.loop)

        ctk.CTkLabel(
            self._editor_frame, text="Настройки скрипта",
            font=ctk.CTkFont(weight="bold"), text_color="#e8ecf4",
        ).pack(anchor="w", padx=10, pady=(10, 4))

        meta = ctk.CTkFrame(self._editor_frame, fg_color="transparent")
        meta.pack(fill="x", padx=10, pady=(0, 6))

        ctk.CTkLabel(meta, text="Имя", width=40, anchor="w").pack(side="left")
        name_entry = ctk.CTkEntry(meta, textvariable=self._name_var, width=160)
        name_entry.pack(side="left", padx=(0, 10))
        name_entry.bind("<FocusOut>", lambda _e: self._apply_editor_to_selected())

        ctk.CTkLabel(meta, text="Hotkey", width=50, anchor="w").pack(side="left")
        hotkey_entry = ctk.CTkEntry(meta, textvariable=self._hotkey_var, width=90)
        hotkey_entry.pack(side="left", padx=(0, 6))
        hotkey_entry.bind("<FocusOut>", lambda _e: self._apply_editor_to_selected(reload_hotkeys=True))
        ctk.CTkButton(
            meta, text="Применить", width=80, height=26,
            fg_color="#3d4659", hover_color="#4d5669",
            command=lambda: self._apply_editor_to_selected(reload_hotkeys=True),
        ).pack(side="left", padx=(0, 10))

        ctk.CTkCheckBox(
            meta, text="Зациклить", variable=self._loop_var,
            command=self._apply_editor_to_selected,
            fg_color="#c45c26", hover_color="#a04a1e",
        ).pack(side="left")

        steps_header = ctk.CTkFrame(self._editor_frame, fg_color="transparent")
        steps_header.pack(fill="x", padx=10, pady=(4, 4))
        ctk.CTkLabel(
            steps_header, text="Шаги",
            font=ctk.CTkFont(weight="bold"), text_color="#e8ecf4",
        ).pack(side="left")
        ctk.CTkButton(
            steps_header, text="+ Клик", width=70, height=26,
            fg_color="#c45c26", hover_color="#a04a1e",
            command=self._add_click_step,
        ).pack(side="right", padx=(6, 0))
        ctk.CTkButton(
            steps_header, text="+ Пауза", width=70, height=26,
            fg_color="#3d4659", hover_color="#4d5669",
            command=self._add_delay_step,
        ).pack(side="right")

        self._steps_frame = ctk.CTkFrame(self._editor_frame, fg_color="#10151f", corner_radius=6)
        self._steps_frame.pack(fill="x", padx=10, pady=(0, 10))
        self._refresh_steps()

    def _refresh_steps(self) -> None:
        if not self._steps_frame:
            return
        for w in self._steps_frame.winfo_children():
            w.destroy()
        script = self._selected()
        if script is None:
            return
        if not script.steps:
            ctk.CTkLabel(
                self._steps_frame, text="Добавьте клик или паузу",
                text_color="#6b7280",
            ).pack(pady=12)
            return

        for index, step in enumerate(script.steps):
            self._build_step_row(script, index, step)

    def _build_step_row(self, script: ClickScript, index: int, step: ScriptStep) -> None:
        assert self._steps_frame is not None
        card = ctk.CTkFrame(self._steps_frame, fg_color="#161c2a", corner_radius=4)
        card.pack(fill="x", padx=4, pady=3)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=8, pady=(6, 2))
        kind_label = "Клик" if step.kind == "click" else "Пауза"
        ctk.CTkLabel(
            head, text=f"{index + 1}. {kind_label}",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="#e8ecf4",
        ).pack(side="left")

        ctk.CTkButton(
            head, text="↓", width=26, height=24, fg_color="#3d4659",
            command=lambda i=index: self._move_step(i, 1),
        ).pack(side="right", padx=(4, 0))
        ctk.CTkButton(
            head, text="↑", width=26, height=24, fg_color="#3d4659",
            command=lambda i=index: self._move_step(i, -1),
        ).pack(side="right")
        ctk.CTkButton(
            head, text="✕", width=26, height=24,
            fg_color="#4a2230", hover_color="#6a2f42",
            command=lambda i=index: self._remove_step(i),
        ).pack(side="right", padx=(0, 4))

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="x", padx=8, pady=(0, 8))

        if step.kind == "delay":
            self._int_field(body, "мс", step.delay_ms, 70, lambda v, i=index: self._update_step(i, delay_ms=max(0, v)))
            return

        coords = ctk.CTkFrame(body, fg_color="transparent")
        coords.pack(fill="x", pady=2)
        self._int_field(coords, "X", step.x, 60, lambda v, i=index: self._update_step(i, x=v), pack_side="left")
        self._int_field(coords, "Y", step.y, 60, lambda v, i=index: self._update_step(i, y=v), pack_side="left")
        ctk.CTkButton(
            coords, text="Указать", width=70, height=26,
            fg_color="#3d4659", hover_color="#4d5669",
            command=lambda i=index: self._pick_point(i),
        ).pack(side="left", padx=(6, 0))

        opts = ctk.CTkFrame(body, fg_color="transparent")
        opts.pack(fill="x", pady=2)

        btn_var = ctk.StringVar(value=MOUSE_BUTTON_LABELS.get(step.mouse_button, "ЛКМ"))
        label_to_btn = {v: k for k, v in MOUSE_BUTTON_LABELS.items()}
        ctk.CTkLabel(opts, text="Кнопка", width=50, anchor="w", font=ctk.CTkFont(size=11)).pack(side="left")
        ctk.CTkOptionMenu(
            opts, variable=btn_var,
            values=[MOUSE_BUTTON_LABELS[b] for b in MOUSE_BUTTONS],
            width=70, height=26, fg_color="#2a3142", button_color="#3d4659",
            command=lambda val, i=index, m=label_to_btn: self._update_step(i, mouse_button=m.get(val, "left")),
        ).pack(side="left", padx=(0, 8))

        self._int_field(opts, "каждые мс", step.interval_ms, 70, lambda v, i=index: self._update_step(i, interval_ms=max(1, v)), pack_side="left")
        self._int_field(opts, "раз", step.click_count, 50, lambda v, i=index: self._update_step(i, click_count=max(1, v)), pack_side="left")

        hold_row = ctk.CTkFrame(body, fg_color="transparent")
        hold_row.pack(fill="x", pady=2)
        ctk.CTkLabel(hold_row, text="Зажать", width=50, anchor="w", font=ctk.CTkFont(size=11)).pack(side="left")
        hold_labels = [label for _, label in HOLD_KEYS]
        hold_var = ctk.StringVar(value=HOLD_KEY_LABELS.get(step.hold_key, "Нет"))
        ctk.CTkOptionMenu(
            hold_row,
            variable=hold_var,
            values=hold_labels,
            width=110,
            height=26,
            fg_color="#2a3142",
            button_color="#3d4659",
            command=lambda val, i=index: self._update_step(
                i, hold_key=HOLD_KEY_VALUES.get(val, "")
            ),
        ).pack(side="left")

    def _int_field(
        self,
        parent: ctk.CTkFrame,
        label: str,
        value: int,
        width: int,
        on_change,
        pack_side: str = "left",
    ) -> None:
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.pack(side=pack_side, padx=(0, 8))
        ctk.CTkLabel(box, text=label, font=ctk.CTkFont(size=11), text_color="#a0a8b8").pack(side="left", padx=(0, 4))
        var = ctk.StringVar(value=str(value))
        entry = ctk.CTkEntry(box, textvariable=var, width=width, height=26)
        entry.pack(side="left")

        def commit(_event=None) -> None:
            try:
                on_change(int(var.get().strip()))
            except ValueError:
                pass

        entry.bind("<FocusOut>", commit)
        entry.bind("<Return>", commit)

    def _apply_editor_to_selected(self, reload_hotkeys: bool = False) -> None:
        script = self._selected()
        if script is None:
            return
        script.name = self._name_var.get().strip() or script.name
        script.hotkey = self._hotkey_var.get().strip().lower()
        script.loop = bool(self._loop_var.get())
        self._save()
        if reload_hotkeys:
            self._reload_hotkeys()
        self._refresh_scripts_list()

    def _update_step(self, index: int, **kwargs) -> None:
        script = self._selected()
        if script is None or not (0 <= index < len(script.steps)):
            return
        step = script.steps[index]
        for key, value in kwargs.items():
            setattr(step, key, value)
        self._save()
        self._refresh_scripts_list()

    def _add_click_step(self) -> None:
        script = self._selected()
        if script is None:
            return
        self._apply_editor_to_selected()
        script.steps.append(
            ScriptStep(kind="click", x=960, y=540, interval_ms=200, click_count=1)
        )
        self._save()
        self._refresh_all()

    def _add_delay_step(self) -> None:
        script = self._selected()
        if script is None:
            return
        self._apply_editor_to_selected()
        script.steps.append(ScriptStep(kind="delay", delay_ms=1000))
        self._save()
        self._refresh_all()

    def _remove_step(self, index: int) -> None:
        script = self._selected()
        if script is None or not (0 <= index < len(script.steps)):
            return
        del script.steps[index]
        self._save()
        self._refresh_all()

    def _move_step(self, index: int, delta: int) -> None:
        script = self._selected()
        if script is None:
            return
        target = index + delta
        if not (0 <= index < len(script.steps) and 0 <= target < len(script.steps)):
            return
        script.steps[index], script.steps[target] = script.steps[target], script.steps[index]
        self._save()
        self._refresh_all()

    def _pick_point(self, index: int) -> None:
        self._pick_step_index = index
        self._status_var.set("Укажи точку на экране…")
        was_visible = self._overlay.root.winfo_viewable()
        if was_visible:
            self._overlay.hide()

        def on_picked(x: int, y: int) -> None:
            step_index = self._pick_step_index
            self._pick_step_index = None
            if step_index is not None:
                self._update_step(step_index, x=x, y=y)
            self._status_var.set(f"Точка: ({x}, {y})")
            if was_visible:
                self._overlay.root.after(50, self._overlay.show)
            self._overlay.root.after(80, self._refresh_all)

        def on_cancel() -> None:
            self._pick_step_index = None
            self._status_var.set("Выбор точки отменён")
            if was_visible:
                self._overlay.root.after(50, self._overlay.show)

        self._overlay.root.after(120, lambda: self._picker.pick(on_picked, on_cancel))

    def _refresh_all(self) -> None:
        self._refresh_scripts_list()
        self._refresh_editor()
        self.request_resize()

    # --- run / hotkeys ---

    def _start_selected(self) -> None:
        self._apply_editor_to_selected()
        script = self._selected()
        if script is None:
            self._status_var.set("Нет выбранного скрипта")
            return
        self._start_script(script)

    def _start_script(self, script: ClickScript) -> None:
        if self._engine.running_script_id == script.id:
            self._engine.stop()
            return
        ok = self._engine.start(script)
        if ok:
            self._overlay.show_live_alert(f"Скрипт «{script.name}» запущен")
            self._refresh_scripts_list()
        else:
            self._status_var.set("Не удалось запустить")

    def _stop_engine(self) -> None:
        if self._engine.is_running:
            self._engine.stop()
            self._status_var.set("Остановка…")
        else:
            self._status_var.set("Не запущено")

    def _toggle_script_by_id(self, script_id: str) -> None:
        script = next((s for s in self._scripts if s.id == script_id), None)
        if script is None:
            return
        if self._engine.running_script_id == script_id:
            self._engine.stop()
            return
        self._overlay.root.after(0, lambda: self._start_script(script))

    def _on_engine_status(self, message: str) -> None:
        self._overlay.root.after(0, lambda: self._status_var.set(message))

    def _on_engine_finished(self) -> None:
        def update() -> None:
            self._refresh_scripts_list()
            self._overlay.show_live_alert(self._status_var.get())

        self._overlay.root.after(0, update)

    def _unload_hotkeys(self) -> None:
        for handle in self._hotkey_handles:
            try:
                keyboard.remove_hotkey(handle)
            except Exception:
                pass
        self._hotkey_handles.clear()

    def _reload_hotkeys(self) -> None:
        self._unload_hotkeys()
        for script in self._scripts:
            if not script.hotkey:
                continue
            try:
                handle = keyboard.add_hotkey(
                    script.hotkey,
                    lambda sid=script.id: self._toggle_script_by_id(sid),
                    suppress=False,
                )
                self._hotkey_handles.append(handle)
            except Exception:
                continue
