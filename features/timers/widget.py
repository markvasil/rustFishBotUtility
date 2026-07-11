from __future__ import annotations

import winsound
from typing import Dict, List, Optional

import customtkinter as ctk

from features.base import Feature
from features.resource_machines.calculator import format_duration
from features.shared_data import DECAY_HOURS, MACHINES
from services.timer_manager import ActiveTimer, TimerManager
from storage.session import SessionStore


class TimersFeature(Feature):
    id = "timers"
    title = "Таймеры"

    def __init__(self, session: SessionStore, timer_manager: TimerManager) -> None:
        super().__init__()
        self._session = session
        self._timers = timer_manager
        self._title_var: Optional[ctk.StringVar] = None
        self._minutes_var: Optional[ctk.StringVar] = None
        self._decay_var = ctk.StringVar(value="")
        self._machine_var: Optional[ctk.StringVar] = None
        self._diesel_var: Optional[ctk.StringVar] = None
        self._list_frame: Optional[ctk.CTkFrame] = None

    def build(self, parent: ctk.CTkFrame) -> None:
        self._title_var = ctk.StringVar(value="Проверить печи")
        self._minutes_var = ctk.StringVar(value="10")
        decay_labels = [f"{v[0]} ({v[1]:.0f} ч)" for v in DECAY_HOURS.values()]
        self._decay_labels_map = dict(zip(decay_labels, DECAY_HOURS.keys()))
        self._decay_var = ctk.StringVar(value=decay_labels[2])
        self._machine_var = ctk.StringVar(value=list(MACHINES.keys())[0])
        self._diesel_var = ctk.StringVar(value="5")

        ctk.CTkLabel(
            parent, text="Таймеры с уведомлением (звук + показ оверлея)",
            font=ctk.CTkFont(size=13), text_color="#a0a8b8",
        ).pack(anchor="w", padx=12, pady=(12, 8))

        # Напоминание
        block1 = ctk.CTkFrame(parent, fg_color="#1a2030", corner_radius=8)
        block1.pack(fill="x", padx=12, pady=(0, 6))
        ctk.CTkLabel(block1, text="Напоминание", font=ctk.CTkFont(weight="bold"),
                     text_color="#e8ecf4").pack(anchor="w", padx=10, pady=(8, 4))
        r1 = ctk.CTkFrame(block1, fg_color="transparent")
        r1.pack(fill="x", padx=10, pady=(0, 8))
        ctk.CTkEntry(r1, textvariable=self._title_var, width=180).pack(side="left", padx=(0, 8))
        ctk.CTkEntry(r1, textvariable=self._minutes_var, width=50).pack(side="left")
        ctk.CTkLabel(r1, text="мин").pack(side="left", padx=4)
        ctk.CTkButton(r1, text="Старт", width=80, fg_color="#c45c26",
                      command=self._start_reminder).pack(side="left", padx=8)

        # Декей
        block2 = ctk.CTkFrame(parent, fg_color="#1a2030", corner_radius=8)
        block2.pack(fill="x", padx=12, pady=(0, 6))
        ctk.CTkLabel(block2, text="Декей (без upkeep)", font=ctk.CTkFont(weight="bold"),
                     text_color="#e8ecf4").pack(anchor="w", padx=10, pady=(8, 4))
        r2 = ctk.CTkFrame(block2, fg_color="transparent")
        r2.pack(fill="x", padx=10, pady=(0, 8))
        ctk.CTkOptionMenu(r2, variable=self._decay_var, values=decay_labels, width=200,
                          fg_color="#2a3142", button_color="#3d4659").pack(side="left", padx=(0, 8))
        ctk.CTkButton(r2, text="Старт", width=80, fg_color="#c45c26",
                      command=self._start_decay).pack(side="left")

        # Машины
        block3 = ctk.CTkFrame(parent, fg_color="#1a2030", corner_radius=8)
        block3.pack(fill="x", padx=12, pady=(0, 6))
        ctk.CTkLabel(block3, text="Экскаватор / карьер / качалка", font=ctk.CTkFont(weight="bold"),
                     text_color="#e8ecf4").pack(anchor="w", padx=10, pady=(8, 4))
        r3 = ctk.CTkFrame(block3, fg_color="transparent")
        r3.pack(fill="x", padx=10, pady=(0, 8))
        machine_names = [MACHINES[k]["name"] for k in MACHINES]
        self._machine_name_to_id = {MACHINES[k]["name"]: k for k in MACHINES}
        self._machine_var.set(machine_names[0])
        ctk.CTkOptionMenu(r3, variable=self._machine_var, values=machine_names, width=220,
                          fg_color="#2a3142", button_color="#3d4659").pack(side="left", padx=(0, 8))
        ctk.CTkEntry(r3, textvariable=self._diesel_var, width=50).pack(side="left")
        ctk.CTkLabel(r3, text="дизель").pack(side="left", padx=4)
        ctk.CTkButton(r3, text="Старт", width=80, fg_color="#c45c26",
                      command=self._start_machine).pack(side="left", padx=8)

        ctk.CTkLabel(parent, text="Активные таймеры", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#8b93a7").pack(anchor="w", padx=12, pady=(8, 4))
        self._list_frame = ctk.CTkFrame(parent, fg_color="#10151f", corner_radius=6)
        self._list_frame.pack(fill="x", padx=12, pady=(0, 12))
        self._timers.set_on_tick(self._on_timer_tick)
        self._refresh()

    def _parse_minutes(self) -> int:
        try:
            return max(1, int(self._minutes_var.get().strip()))
        except (ValueError, AttributeError):
            return 10

    def _parse_diesel(self) -> int:
        try:
            return max(1, int(self._diesel_var.get().strip()))
        except (ValueError, AttributeError):
            return 1

    def _start_reminder(self) -> None:
        title = self._title_var.get().strip() if self._title_var else "Напоминание"
        self._timers.add(title, self._parse_minutes() * 60)
        self._persist_timers()
        self._refresh()

    def _start_decay(self) -> None:
        label = self._decay_var.get()
        tier_id = self._decay_labels_map.get(label, "stone")
        name, hours = DECAY_HOURS[tier_id]
        self._timers.add(f"Декей: {name}", hours * 3600)
        self._persist_timers()
        self._refresh()

    def _start_machine(self) -> None:
        mid = self._machine_name_to_id.get(self._machine_var.get(), "excavator_stone")
        diesel = self._parse_diesel()
        seconds = MACHINES[mid]["diesel_seconds"] * diesel
        name = MACHINES[mid]["name"]
        self._timers.add(f"{name} ({diesel} диз.)", seconds)
        self._persist_timers()
        self._refresh()

    def _persist_timers(self) -> None:
        self._session.update_feature("timers", active=self._timers.dump())

    def _cancel(self, timer_id: str) -> None:
        self._timers.remove(timer_id)
        self._persist_timers()
        self._refresh()

    def _on_timer_tick(self) -> None:
        if self._list_frame and self._list_frame.winfo_exists():
            self._refresh()

    def _refresh(self) -> None:
        if not self._list_frame:
            return
        for w in self._list_frame.winfo_children():
            w.destroy()
        timers = self._timers.list_active()
        if not timers:
            ctk.CTkLabel(self._list_frame, text="Нет активных таймеров", text_color="#6b7280").pack(pady=16)
        else:
            for timer in timers:
                row = ctk.CTkFrame(self._list_frame, fg_color="#161c2a", corner_radius=4)
                row.pack(fill="x", pady=2)
                ctk.CTkLabel(
                    row,
                    text=f"{timer.title} — {format_duration(timer.remaining)}",
                    anchor="w", font=ctk.CTkFont(size=12), text_color="#d1d7e3",
                ).pack(side="left", padx=8, pady=6)
                ctk.CTkButton(row, text="✕", width=28, height=28,
                              fg_color="#4a2230", hover_color="#6a2f42",
                              command=lambda tid=timer.id: self._cancel(tid)).pack(side="right", padx=4)
        self.request_resize()

    @staticmethod
    def on_timer_complete(timer: ActiveTimer, show_overlay) -> None:
        try:
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass
        show_overlay()
