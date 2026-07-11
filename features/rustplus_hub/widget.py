from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import customtkinter as ctk
from PIL import Image

from features.base import Feature
from features.rustplus_hub.ui_theme import (
    Theme,
    btn_danger,
    btn_primary,
    btn_secondary,
    card,
    hint_label,
    panel,
    section_header,
    set_pill,
    status_pill,
    step_card,
)
from features.rustplus_hub.map_window import MapWindow
from features.rustplus_hub.minimap_window import MinimapWindow
from services.rustplus.event_bus import EventType, RustPlusEvent
from services.rustplus.live_format import filter_vendors, upkeep_hours_left
from services.rustplus.service import RustPlusService
from storage.rustplus_store import AlertSettings, PairedServer

if TYPE_CHECKING:
    from features.crosshair.window import CrosshairWindow
    from overlay.window import OverlayWindow

class RustPlusHubFeature(Feature):
    id = "rustplus"
    title = "Rust+ Live"
    MAP_PREVIEW_MAX = (560, 420)
    LIVE_SCROLL_HEIGHT = 380
    SERVER_ROW_HEIGHT = 54
    SERVERS_MAX_VISIBLE = 2

    def __init__(
        self,
        service: RustPlusService,
        overlay: "OverlayWindow",
        crosshair: Optional["CrosshairWindow"] = None,
    ) -> None:
        super().__init__()
        self._service = service
        self._overlay = overlay
        self._crosshair = crosshair
        self._root = overlay.root
        self._status_label: Optional[ctk.CTkLabel] = None
        self._status_pills: Dict[str, ctk.CTkLabel] = {}
        self._manual_body: Optional[ctk.CTkFrame] = None
        self._manual_visible = False
        self._info_label: Optional[ctk.CTkLabel] = None
        self._servers_frame: Optional[ctk.CTkFrame] = None
        self._manual_ip: Optional[ctk.StringVar] = None
        self._manual_port: Optional[ctk.StringVar] = None
        self._manual_player_id: Optional[ctk.StringVar] = None
        self._manual_token: Optional[ctk.StringVar] = None
        self._manual_name: Optional[ctk.StringVar] = None
        self._chat_frame: Optional[ctk.CTkFrame] = None
        self._chat_input: Optional[ctk.CTkEntry] = None
        self._poll_job: Optional[str] = None
        self._live_scroll: Optional[ctk.CTkScrollableFrame] = None
        self._team_frame: Optional[ctk.CTkFrame] = None
        self._events_frame: Optional[ctk.CTkFrame] = None
        self._vendors_frame: Optional[ctk.CTkFrame] = None
        self._devices_frame: Optional[ctk.CTkFrame] = None
        self._vendor_search: Optional[ctk.StringVar] = None
        self._map_preview: Optional[ctk.CTkLabel] = None
        self._map_image_ref: Optional[ctk.CTkImage] = None
        self._vendors_cache: List[Dict[str, Any]] = []
        self._device_states: Dict[int, Dict[str, Any]] = {}
        self._server_time: str = ""
        self._map_path: Optional[str] = None
        self._map_size: Optional[int] = None
        self._team_cache: List[Dict[str, Any]] = []
        self._map_window: Optional[MapWindow] = None
        self._events_cache: List[Dict[str, Any]] = []
        self._server_time_raw: Optional[float] = None
        pos = service.store.get_minimap_position()
        initial_pos = (pos[0], pos[1]) if pos[0] is not None and pos[1] is not None else None
        self._minimap = MinimapWindow(
            overlay.root,
            initial_position=initial_pos,
            on_position_changed=lambda x, y: service.store.set_minimap_position(x, y),
            renderer=service.map_renderer,
        )
        self._camera_window: Optional[CameraWindow] = None
        self._cameras_frame: Optional[ctk.CTkFrame] = None
        self._camera_input: Optional[ctk.StringVar] = None
        self._alerts_frame: Optional[ctk.CTkFrame] = None
        self._alerts_log: List[str] = []

        for event_type in EventType:
            self._service.event_bus.subscribe(event_type, self._on_event)

    def build(self, parent: ctk.CTkFrame) -> None:
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(12, 6))
        ctk.CTkLabel(
            header,
            text="Rust+ Live",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=Theme.TEXT,
        ).pack(anchor="w")
        ctk.CTkLabel(
            header,
            text="Подключение → мониторинг → карта и устройства",
            font=ctk.CTkFont(size=11),
            text_color=Theme.MUTED,
        ).pack(anchor="w", pady=(2, 0))

        status_bar = card(parent, alt=True)
        status_bar.pack(fill="x", padx=12, pady=(0, 6))
        pills_row = ctk.CTkFrame(status_bar, fg_color="transparent")
        pills_row.pack(fill="x", padx=10, pady=8)
        for key in ("FCM", "Node", "Listener", "Сервер"):
            pill = status_pill(pills_row, key)
            pill.pack(side="left", padx=(0, 6))
            self._status_pills[key] = pill

        self._status_label = ctk.CTkLabel(
            status_bar,
            text="",
            font=ctk.CTkFont(size=10),
            text_color=Theme.DIM,
            anchor="w",
            justify="left",
            wraplength=540,
        )
        self._status_label.pack(fill="x", padx=10, pady=(0, 8))

        self._tabs = ctk.CTkTabview(
            parent,
            width=580,
            height=520,
            fg_color=Theme.SURFACE,
            segmented_button_fg_color=Theme.CARD,
            segmented_button_selected_color=Theme.ACCENT_DARK,
            segmented_button_selected_hover_color=Theme.ACCENT,
            segmented_button_unselected_color=Theme.CARD_ALT,
            segmented_button_unselected_hover_color=Theme.BORDER,
            text_color=Theme.TEXT,
        )
        self._tabs.pack(fill="x", padx=12, pady=(0, 8))

        tab_connect = self._tabs.add("Подключение")
        tab_live = self._tabs.add("Live")
        tab_map = self._tabs.add("Карта")
        tab_devices = self._tabs.add("Устройства")
        tab_settings = self._tabs.add("Настройки")

        self._build_connect_tab(tab_connect)
        self._build_live_tab(tab_live)
        self._build_map_tab(tab_map)
        self._build_devices_tab(tab_devices)
        self._build_settings_tab(tab_settings)

        self._refresh_status()
        self._refresh_servers()
        self._start_event_pump()

    def _build_connect_tab(self, parent: ctk.CTkFrame) -> None:
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent", corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=4, pady=4)

        def step1(body: ctk.CTkFrame) -> None:
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x")
            btn_primary(row, "Steam Chrome", lambda: self._register_fcm("chrome"), width=118).pack(side="left", padx=(0, 6))
            btn_secondary(row, "Steam Edge", lambda: self._register_fcm("edge"), width=118).pack(side="left", padx=(0, 6))
            btn_danger(row, "Сброс", self._reset_fcm, width=72).pack(side="left")
            hint_label(body, "Разрешите popups для localhost. При ошибке login попробуйте Edge.")

        def step2(body: ctk.CTkFrame) -> None:
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x")
            btn_primary(row, "Старт listener", self._start_listener, width=120).pack(side="left", padx=(0, 6))
            btn_secondary(row, "Стоп", self._stop_listener, width=80).pack(side="left")
            hint_label(body, "После Pair Server нажмите Resend notification (listener активен).", warn=True)
            hint_label(body, "Закройте мобильный Rust+ — одновременная работа ломает паринг.", warn=True)

        step_card(scroll, 1, "Регистрация FCM (Steam)", step1)
        step_card(scroll, 2, "Listener и Pair в игре", step2)

        servers_card = card(scroll)
        servers_card.pack(fill="x", padx=4, pady=(0, 8))
        head = ctk.CTkFrame(servers_card, fg_color="transparent")
        head.pack(fill="x", padx=12, pady=(10, 6))
        ctk.CTkLabel(head, text="3. Серверы", font=ctk.CTkFont(size=12, weight="bold"), text_color=Theme.TEXT).pack(side="left")
        btn_secondary(head, "Обновить", self._refresh_servers, width=90, height=26).pack(side="right")
        self._servers_outer = panel(servers_card)
        self._servers_outer.pack(fill="x", padx=12, pady=(0, 6))
        self._servers_outer.pack_propagate(False)
        self._servers_frame = ctk.CTkScrollableFrame(
            self._servers_outer,
            fg_color="transparent",
            corner_radius=0,
            height=self.SERVER_ROW_HEIGHT + 8,
            scrollbar_button_color=Theme.BORDER,
        )
        self._servers_frame.pack(fill="both", expand=True, padx=2, pady=2)
        hint_label(servers_card, "Connect работает только когда вы онлайн на сервере в игре.")
        ctk.CTkFrame(servers_card, fg_color="transparent", height=4).pack()

        manual_toggle = ctk.CTkFrame(scroll, fg_color="transparent")
        manual_toggle.pack(fill="x", padx=4, pady=(0, 4))
        btn_secondary(
            manual_toggle,
            "▸ Добавить сервер вручную",
            self._toggle_manual_panel,
            width=200,
            height=28,
        ).pack(anchor="w")

        self._manual_body = card(scroll)
        self._manual_body.pack(fill="x", padx=4, pady=(0, 8))
        if not self._manual_visible:
            self._manual_body.pack_forget()

        ctk.CTkLabel(
            self._manual_body,
            text="Ручной ввод pairing-данных",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=Theme.MUTED,
        ).pack(anchor="w", padx=12, pady=(10, 6))
        self._manual_name = ctk.StringVar(value="Мой сервер")
        self._manual_ip = ctk.StringVar(value="")
        self._manual_port = ctk.StringVar(value="28082")
        self._manual_player_id = ctk.StringVar(value="")
        self._manual_token = ctk.StringVar(value="")
        mr = ctk.CTkFrame(self._manual_body, fg_color="transparent")
        mr.pack(fill="x", padx=12, pady=(0, 12))
        for label, var, width in [
            ("IP", self._manual_ip, 120),
            ("Порт", self._manual_port, 60),
            ("Steam ID", self._manual_player_id, 130),
            ("Token", self._manual_token, 80),
        ]:
            f = ctk.CTkFrame(mr, fg_color="transparent")
            f.pack(side="left", padx=(0, 8))
            ctk.CTkLabel(f, text=label, font=ctk.CTkFont(size=10), text_color=Theme.DIM).pack(anchor="w")
            ctk.CTkEntry(f, textvariable=var, width=width, height=28, corner_radius=8).pack()
        btn_primary(mr, "Добавить", self._add_manual_server, width=90).pack(side="left", padx=(4, 0))

        info_card = card(scroll, alt=True)
        info_card.pack(fill="x", padx=4, pady=(0, 8))
        ctk.CTkLabel(
            info_card,
            text="Статус подключения",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=Theme.MUTED,
        ).pack(anchor="w", padx=12, pady=(10, 4))
        self._info_label = ctk.CTkLabel(
            info_card,
            text="Не подключено",
            font=ctk.CTkFont(size=12),
            text_color=Theme.INFO,
            anchor="w",
            justify="left",
        )
        self._info_label.pack(fill="x", padx=12, pady=(0, 12))

    def _build_live_tab(self, parent: ctk.CTkFrame) -> None:
        self._live_scroll = ctk.CTkScrollableFrame(
            parent,
            fg_color="transparent",
            corner_radius=0,
            height=self.LIVE_SCROLL_HEIGHT,
        )
        self._live_scroll.pack(fill="x", padx=4, pady=(4, 0))
        self._build_team_section(self._live_scroll)
        self._build_events_section(self._live_scroll)
        self._build_alerts_section(self._live_scroll)

        chat_card = card(parent)
        chat_card.pack(fill="x", padx=4, pady=8)
        ctk.CTkLabel(
            chat_card,
            text="Team chat",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=Theme.MUTED,
        ).pack(anchor="w", padx=12, pady=(8, 4))
        self._chat_frame = panel(chat_card)
        self._chat_frame.pack(fill="x", padx=12, pady=(0, 8))
        chat_row = ctk.CTkFrame(chat_card, fg_color="transparent")
        chat_row.pack(fill="x", padx=12, pady=(0, 12))
        self._chat_input = ctk.CTkEntry(
            chat_row,
            placeholder_text="Сообщение в team chat",
            height=32,
            corner_radius=8,
        )
        self._chat_input.pack(side="left", fill="x", expand=True, padx=(0, 8))
        btn_primary(chat_row, "Отправить", self._send_chat, width=100, height=32).pack(side="left")

    def _build_map_tab(self, parent: ctk.CTkFrame) -> None:
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent", corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=4, pady=4)
        self._build_map_section(scroll)
        self._build_vendors_section(scroll)

    def _build_devices_tab(self, parent: ctk.CTkFrame) -> None:
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent", corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=4, pady=4)
        self._build_devices_section(scroll)
        self._build_cameras_section(scroll)

    def _build_settings_tab(self, parent: ctk.CTkFrame) -> None:
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent", corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=4, pady=4)
        self._build_settings_section(scroll)

    def _toggle_manual_panel(self) -> None:
        if not self._manual_body:
            return
        self._manual_visible = not self._manual_visible
        if self._manual_visible:
            self._manual_body.pack(fill="x", padx=4, pady=(0, 8))
        else:
            self._manual_body.pack_forget()
        self.request_resize()

    def on_show(self) -> None:
        self._refresh_status()
        self._refresh_servers()
        self._refresh_devices_panel()
        self._refresh_cameras_panel()
        self._refresh_fcm_warning()
        self._refresh_groups_label()
        if self._service.connection.is_connected:
            self._service.refresh_device_states()

    def _section_title(self, parent: ctk.CTkFrame, text: str, subtitle: Optional[str] = None) -> None:
        section_header(parent, text, subtitle)

    def _build_team_section(self, parent: ctk.CTkScrollableFrame) -> None:
        self._section_title(parent, "Команда", "Онлайн, грид и статус")
        self._team_frame = panel(parent)
        self._team_frame.pack(fill="x", padx=4, pady=(0, 8))
        ctk.CTkLabel(
            self._team_frame, text="Подключитесь к серверу", text_color=Theme.DIM,
        ).pack(anchor="w", padx=10, pady=10)

    def _build_events_section(self, parent: ctk.CTkScrollableFrame) -> None:
        self._section_title(parent, "События", "Клик — трекинг на карте")
        self._events_frame = panel(parent)
        self._events_frame.pack(fill="x", padx=4, pady=(0, 8))
        ctk.CTkLabel(
            self._events_frame, text="Нет активных событий", text_color=Theme.DIM,
        ).pack(anchor="w", padx=10, pady=10)

    def _build_alerts_section(self, parent: ctk.CTkScrollableFrame) -> None:
        self._section_title(parent, "Журнал алертов", "Toast + история")
        self._alerts_frame = panel(parent)
        self._alerts_frame.pack(fill="x", padx=4, pady=(0, 8))
        ctk.CTkLabel(
            self._alerts_frame,
            text="Карго, смерть, магазины, Smart Alarm",
            text_color=Theme.DIM,
            font=ctk.CTkFont(size=10),
        ).pack(anchor="w", padx=10, pady=10)

    def _build_vendors_section(self, parent: ctk.CTkScrollableFrame) -> None:
        self._section_title(parent, "Магазины", "Поиск по названию или item id")
        search_row = ctk.CTkFrame(parent, fg_color="transparent")
        search_row.pack(fill="x", padx=4, pady=(0, 6))
        self._vendor_search = ctk.StringVar()
        entry = ctk.CTkEntry(
            search_row,
            textvariable=self._vendor_search,
            placeholder_text="Название или item id",
            height=30,
            corner_radius=8,
        )
        entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        btn_secondary(search_row, "Найти", self._search_vendors, width=72, height=30).pack(side="left")
        self._vendors_frame = panel(parent)
        self._vendors_frame.pack(fill="x", padx=4, pady=(0, 8))
        ctk.CTkLabel(
            self._vendors_frame, text="Нет магазинов", text_color=Theme.DIM,
        ).pack(anchor="w", padx=10, pady=10)

    def _build_devices_section(self, parent: ctk.CTkScrollableFrame) -> None:
        section_header(
            parent,
            "Умные устройства",
            "Switch, Alarm, Storage Monitor",
            action_text="Обновить",
            action_command=lambda: self._service.refresh_device_states(),
        )
        self._devices_frame = panel(parent)
        self._devices_frame.pack(fill="x", padx=4, pady=(0, 8))
        self._refresh_devices_panel()

    def _build_cameras_section(self, parent: ctk.CTkScrollableFrame) -> None:
        self._section_title(parent, "Камеры", "CCTV / PTZ — DOME1, OILRIG1L1…")
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=4, pady=(0, 6))
        self._camera_input = ctk.StringVar()
        ctk.CTkEntry(
            row, textvariable=self._camera_input, placeholder_text="ID камеры", height=30, corner_radius=8,
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))
        btn_primary(row, "Открыть", self._open_camera_from_input, width=80, height=30).pack(side="left", padx=(0, 4))
        btn_secondary(row, "Сохранить", self._save_camera_from_input, width=80, height=30).pack(side="left")

        presets = ctk.CTkFrame(parent, fg_color="transparent")
        presets.pack(fill="x", padx=4, pady=(0, 6))
        for cam_id in ("DOME1", "OILRIG1L1", "OILRIG2L1", "AIRFIELD1"):
            btn_secondary(
                presets, cam_id, lambda cid=cam_id: self._open_camera_view(cid), width=88, height=26,
            ).pack(side="left", padx=(0, 4))

        self._cameras_frame = panel(parent)
        self._cameras_frame.pack(fill="x", padx=4, pady=(0, 8))
        self._refresh_cameras_panel()

    def _build_map_section(self, parent: ctk.CTkScrollableFrame) -> None:
        self._section_title(parent, "Карта", "Миникарта: ЛКМ drag, ПКМ скрыть")
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=4, pady=(0, 6))
        btn_secondary(row, "Загрузить", lambda: self._service.fetch_map(), width=100, height=30).pack(side="left", padx=(0, 4))
        btn_primary(row, "Крупно", self._open_map_window, width=90, height=30).pack(side="left", padx=(0, 4))
        btn_secondary(row, "Миникарта", self._toggle_minimap, width=100, height=30).pack(side="left")
        self._map_preview = ctk.CTkLabel(
            parent,
            text="Нажмите «Загрузить»",
            height=self.MAP_PREVIEW_MAX[1] + 8,
            cursor="hand2",
            fg_color=Theme.PANEL,
            corner_radius=10,
        )
        self._map_preview.pack(fill="x", padx=4, pady=(0, 8))
        self._map_preview.bind("<Button-1>", lambda _e: self._open_map_window())

    def _build_settings_section(self, parent: ctk.CTkScrollableFrame) -> None:
        self._section_title(parent, "Настройки", "Алерты, карта, устройства, прицел")
        frame = card(parent)
        frame.pack(fill="x", padx=4, pady=(0, 8))

        alerts = self._service.store.get_alert_settings()
        self._alert_vars = {
            "cargo": ctk.BooleanVar(value=alerts.cargo),
            "death": ctk.BooleanVar(value=alerts.death),
            "shop": ctk.BooleanVar(value=alerts.shop),
            "alarm": ctk.BooleanVar(value=alerts.alarm),
        }
        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=8)
        ctk.CTkLabel(row, text="Алерты на карте и в чате", font=ctk.CTkFont(size=10, weight="bold"), text_color=Theme.MUTED).pack(anchor="w", pady=(0, 6))
        for key, label in [
            ("cargo", "Карго"), ("death", "Смерть"), ("shop", "Магазины"), ("alarm", "Alarm"),
        ]:
            ctk.CTkCheckBox(
                row, text=label, variable=self._alert_vars[key], width=90,
                command=self._save_alert_settings,
            ).pack(side="left", padx=(0, 6))

        settings = self._service.store.get_settings()
        row2 = ctk.CTkFrame(frame, fg_color="transparent")
        row2.pack(fill="x", padx=8, pady=4)
        self._autostart_var = ctk.BooleanVar(value=settings.autostart)
        self._tray_var = ctk.BooleanVar(value=settings.minimize_to_tray)
        self._chat_cmd_var = ctk.BooleanVar(value=settings.chat_commands_enabled)
        ctk.CTkCheckBox(row2, text="Автозапуск", variable=self._autostart_var, command=self._save_app_settings).pack(side="left", padx=(0, 8))
        ctk.CTkCheckBox(row2, text="Tray 24/7", variable=self._tray_var, command=self._save_app_settings).pack(side="left", padx=(0, 8))
        ctk.CTkCheckBox(row2, text="Чат-команды", variable=self._chat_cmd_var, command=self._save_app_settings).pack(side="left")

        row3 = ctk.CTkFrame(frame, fg_color="transparent")
        row3.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(row3, text="Follow:", font=ctk.CTkFont(size=10)).pack(side="left")
        self._follow_var = ctk.StringVar(value="")
        ctk.CTkEntry(row3, textvariable=self._follow_var, width=120, placeholder_text="Steam ID").pack(side="left", padx=6)
        ctk.CTkButton(row3, text="OK", width=40, command=self._save_follow).pack(side="left")

        row4 = ctk.CTkFrame(frame, fg_color="transparent")
        row4.pack(fill="x", padx=8, pady=4)
        ctk.CTkButton(row4, text="Экспорт устройств", width=120, fg_color="#2a3142", command=self._export_devices).pack(side="left", padx=(0, 6))
        ctk.CTkButton(row4, text="Импорт", width=70, fg_color="#2a3142", command=self._import_devices_dialog).pack(side="left", padx=(0, 6))
        ctk.CTkButton(row4, text="Очистить смерти", width=110, fg_color="#3d4659", command=self._clear_deaths).pack(side="left")

        row5 = ctk.CTkFrame(frame, fg_color="transparent")
        row5.pack(fill="x", padx=8, pady=4)
        self._profit_item_var = ctk.StringVar(value="")
        ctk.CTkEntry(row5, textvariable=self._profit_item_var, width=80, placeholder_text="item id").pack(side="left")
        ctk.CTkButton(row5, text="Profit", width=60, fg_color="#2a3142", command=self._show_profit).pack(side="left", padx=6)
        self._profit_label = ctk.CTkLabel(row5, text="", font=ctk.CTkFont(size=10), text_color="#8b93a7")
        self._profit_label.pack(side="left", fill="x", expand=True)

        row6 = ctk.CTkFrame(frame, fg_color="transparent")
        row6.pack(fill="x", padx=8, pady=4)
        self._group_name_var = ctk.StringVar(value="Группа")
        self._hotkey_var = ctk.StringVar(value="f7")
        ctk.CTkEntry(row6, textvariable=self._group_name_var, width=90, placeholder_text="Группа").pack(side="left")
        ctk.CTkButton(row6, text="+ все Switch", width=90, fg_color="#2a3142", command=self._create_switch_group).pack(side="left", padx=4)
        ctk.CTkEntry(row6, textvariable=self._hotkey_var, width=50, placeholder_text="f7").pack(side="left", padx=4)
        ctk.CTkButton(row6, text="Hotkey", width=70, fg_color="#c45c26", command=self._bind_group_hotkey).pack(side="left")
        self._groups_label = ctk.CTkLabel(frame, text="", font=ctk.CTkFont(size=10), text_color="#6b7280", anchor="w")
        self._groups_label.pack(fill="x", padx=8, pady=(0, 4))

        cross = ctk.CTkFrame(frame, fg_color="transparent")
        cross.pack(fill="x", padx=8, pady=4)
        self._crosshair_var = ctk.BooleanVar(value=settings.crosshair_enabled)
        self._cross_size_var = ctk.StringVar(value=str(settings.crosshair_size))
        self._cross_color_var = ctk.StringVar(value=settings.crosshair_color)
        ctk.CTkCheckBox(cross, text="Прицел", variable=self._crosshair_var, command=self._save_crosshair).pack(side="left")
        ctk.CTkEntry(cross, textvariable=self._cross_size_var, width=40).pack(side="left", padx=4)
        ctk.CTkEntry(cross, textvariable=self._cross_color_var, width=70).pack(side="left", padx=4)
        ctk.CTkButton(cross, text="OK", width=40, command=self._save_crosshair).pack(side="left")

        sound_row = ctk.CTkFrame(frame, fg_color="transparent")
        sound_row.pack(fill="x", padx=8, pady=4)
        self._alarm_sound_var = ctk.StringVar(value=settings.alarm_sound_path)
        ctk.CTkLabel(sound_row, text="Звук Alarm:", font=ctk.CTkFont(size=10)).pack(side="left")
        ctk.CTkEntry(sound_row, textvariable=self._alarm_sound_var, width=220).pack(side="left", padx=6)
        ctk.CTkButton(sound_row, text="OK", width=40, command=self._save_alarm_sound).pack(side="left")

        intel_row = ctk.CTkFrame(frame, fg_color="transparent")
        intel_row.pack(fill="x", padx=8, pady=4)
        ctk.CTkButton(
            intel_row, text="Player Intel", width=100, fg_color="#2a3142",
            command=self._show_player_intel,
        ).pack(side="left")
        self._intel_label = ctk.CTkLabel(intel_row, text="", font=ctk.CTkFont(size=10), text_color="#8b93a7")
        self._intel_label.pack(side="left", padx=8)

        self._fcm_warn_label = ctk.CTkLabel(
            frame, text="", font=ctk.CTkFont(size=10), text_color="#f59e0b", anchor="w",
        )
        self._fcm_warn_label.pack(fill="x", padx=8, pady=(0, 8))
        self._refresh_fcm_warning()
        self._refresh_groups_label()

    def _save_alert_settings(self) -> None:
        alerts = AlertSettings(
            cargo=self._alert_vars["cargo"].get(),
            death=self._alert_vars["death"].get(),
            shop=self._alert_vars["shop"].get(),
            alarm=self._alert_vars["alarm"].get(),
        )
        self._service.update_alert_settings(alerts)
        self._sync_map_overlays()
        if self._service.connection.is_connected:
            self._service.fetch_map()

    def _map_overlay_vendors(self) -> List[Dict[str, Any]]:
        if not self._service.store.get_alert_settings().shop:
            return []
        return self._vendors_cache

    def _map_overlay_events(self) -> List[Dict[str, Any]]:
        if not self._service.store.get_alert_settings().cargo:
            return []
        return self._events_cache

    def _map_overlay_deaths(self, server_id: Optional[str]) -> List[Dict[str, Any]]:
        if not self._service.store.get_alert_settings().death:
            return []
        if not server_id:
            return []
        return [m.to_dict() for m in self._service.store.list_death_markers(server_id)]

    def _save_app_settings(self) -> None:
        from services.app.autostart import set_autostart

        settings = self._service.store.get_settings()
        settings.autostart = self._autostart_var.get()
        settings.minimize_to_tray = self._tray_var.get()
        settings.chat_commands_enabled = self._chat_cmd_var.get()
        self._service.update_app_settings(settings)
        set_autostart(settings.autostart)

    def _save_follow(self) -> None:
        raw = self._follow_var.get().strip()
        steam_id = int(raw) if raw.isdigit() else None
        self._service.store.set_follow_steam_id(steam_id)
        self._sync_map_overlays()

    def _save_crosshair(self) -> None:
        settings = self._service.store.get_settings()
        settings.crosshair_enabled = self._crosshair_var.get()
        try:
            settings.crosshair_size = int(self._cross_size_var.get())
        except ValueError:
            pass
        settings.crosshair_color = self._cross_color_var.get().strip() or "#00ff00"
        self._service.update_app_settings(settings)
        if self._crosshair:
            self._crosshair.apply_settings()

    def _save_alarm_sound(self) -> None:
        settings = self._service.store.get_settings()
        settings.alarm_sound_path = self._alarm_sound_var.get().strip()
        self._service.update_app_settings(settings)
        self._set_status("Путь к звуку Alarm сохранён")

    def _show_player_intel(self) -> None:
        follow = self._service.store.get_follow_steam_id()
        if not follow and self._team_cache:
            follow = self._team_cache[0].get("steam_id")
        if not follow:
            self._intel_label.configure(text="Нет данных (укажите Follow Steam ID)")
            return
        prediction = self._service.predict_online(int(follow))
        heat = self._service.heatmap(int(follow))
        top_hours = sorted(heat.items(), key=lambda x: -x[1])[:3]
        heat_text = ", ".join(f"{h}:00×{c}" for h, c in top_hours if c)
        text = prediction or "Мало данных"
        if heat_text:
            text += f" | heat: {heat_text}"
        self._intel_label.configure(text=text)

    def _export_devices(self) -> None:
        server = self._service.get_active_server()
        if not server:
            self._set_status("Нет активного сервера", error=True)
            return
        blob = self._service.store.export_devices(server.id)
        self._root.clipboard_clear()
        self._root.clipboard_append(blob)
        self._set_status("Устройства скопированы в буфер — !import в чате или кнопка Импорт")

    def _import_devices_dialog(self) -> None:
        dialog = ctk.CTkInputDialog(text="Вставьте base64 из !share:", title="Импорт устройств")
        blob = dialog.get_input()
        if not blob:
            return
        server = self._service.get_active_server()
        if not server:
            return
        count = self._service.store.import_devices(server.id, blob.strip())
        self._refresh_devices_panel()
        self._service.connection.refresh_devices()
        self._set_status(f"Импортировано устройств: {count}")

    def _clear_deaths(self) -> None:
        server = self._service.get_active_server()
        self._service.store.clear_death_markers(server.id if server else None)
        self._sync_map_overlays()

    def _show_profit(self) -> None:
        raw = self._profit_item_var.get().strip()
        if not raw.isdigit():
            self._set_status("Укажите числовой item id", error=True)
            return
        trades = self._service.profit_trades(int(raw))
        if not trades:
            self._profit_label.configure(text="Нет выгодных маршрутов")
            return
        first = trades[0]
        self._profit_label.configure(
            text=f"+{first['profit']} | {first['route']}",
        )

    def _create_switch_group(self) -> None:
        server = self._service.get_active_server()
        if not server:
            return
        switches = [d.id for d in self._service.store.list_devices(server.id) if d.device_type == "smart_switch"]
        if not switches:
            self._set_status("Нет Switch для группы", error=True)
            return
        name = self._group_name_var.get().strip() or "Группа"
        self._service.store.add_device_group(server.id, name, switches)
        self._refresh_groups_label()

    def _bind_group_hotkey(self) -> None:
        groups = self._service.store.list_device_groups()
        if not groups:
            self._set_status("Сначала создайте группу", error=True)
            return
        hotkey = self._hotkey_var.get().strip().lower()
        self._service.store.add_device_hotkey(hotkey, groups[-1].id, "toggle")
        self._service.reload_device_hotkeys()
        self._set_status(f"Hotkey {hotkey} → {groups[-1].name}")

    def _refresh_groups_label(self) -> None:
        groups = self._service.store.list_device_groups()
        hotkeys = self._service.store.list_device_hotkeys()
        text = f"Групп: {len(groups)} | Hotkeys: {', '.join(h.hotkey for h in hotkeys) or 'нет'}"
        if hasattr(self, "_groups_label"):
            self._groups_label.configure(text=text)

    def _refresh_fcm_warning(self) -> None:
        if hasattr(self, "_fcm_warn_label"):
            warn = self._service.store.fcm_expiry_warning()
            self._fcm_warn_label.configure(text=warn or "")

    def _sync_map_overlays(self) -> None:
        server = self._service.get_active_server()
        server_id = server.id if server else None
        state = {
            "members": self._team_cache,
            "map_size": self._map_size,
            "death_markers": self._map_overlay_deaths(server_id),
            "drawings": [
                d.to_dict() for d in self._service.store.list_map_drawings(server_id)
            ] if server_id else [],
            "events": self._map_overlay_events(),
            "vendors": self._map_overlay_vendors(),
            "follow_steam_id": self._service.store.get_follow_steam_id(),
            "tracked_event_id": self._service.store.get_tracked_event_id(),
        }
        self._minimap.set_overlay_state(**state)
        if self._map_window and self._map_window.is_open:
            self._map_window.update_state(
                team_members=state["members"],
                map_size=state["map_size"],
                death_markers=state["death_markers"],
                drawings=state["drawings"],
                events=state["events"],
                vendors=state["vendors"],
                follow_steam_id=state["follow_steam_id"],
                tracked_event_id=state["tracked_event_id"],
            )

    def _track_event(self, event_id: Optional[int]) -> None:
        self._service.store.set_tracked_event_id(event_id)
        self._sync_map_overlays()
        if event_id:
            self._set_status(f"Трекинг события #{event_id} на карте")

    def _add_map_drawing(self, x: float, y: float, text: str) -> None:
        server = self._service.get_active_server()
        if not server:
            return
        self._service.store.add_map_drawing(server.id, x, y, text)
        self._sync_map_overlays()

    def _clear_frame(self, frame: Optional[ctk.CTkFrame]) -> None:
        if not frame:
            return
        for child in frame.winfo_children():
            child.destroy()

    def _refresh_team_panel(self, members: List[Dict[str, Any]]) -> None:
        if not self._team_frame:
            return
        self._clear_frame(self._team_frame)
        if not members:
            ctk.CTkLabel(self._team_frame, text="Нет команды", text_color="#6b7280").pack(
                anchor="w", padx=8, pady=8,
            )
            return
        for member in members[:12]:
            online = "онлайн" if member.get("is_online") else "оффлайн"
            alive = "" if member.get("is_alive", True) else " | мёртв"
            ctk.CTkLabel(
                self._team_frame,
                text=f"{member.get('name', '?')} [{member.get('grid', '?')}] — {online}{alive}",
                anchor="w", font=ctk.CTkFont(size=11), text_color="#d1d7e3",
            ).pack(fill="x", padx=8, pady=2)
        self.request_resize()

    def _refresh_events_panel(self, events: List[Dict[str, Any]]) -> None:
        if not self._events_frame:
            return
        self._clear_frame(self._events_frame)
        if not events:
            ctk.CTkLabel(self._events_frame, text="Нет активных событий", text_color="#6b7280").pack(
                anchor="w", padx=8, pady=8,
            )
            return
        for event in events[:10]:
            eid = event.get("id")
            btn = ctk.CTkButton(
                self._events_frame,
                text=f"{event.get('type_name', '?')} — {event.get('grid', '?')} → трек",
                anchor="w",
                height=24,
                fg_color="#1a2030",
                hover_color="#2a3142",
                font=ctk.CTkFont(size=11),
                command=lambda eid=eid: self._track_event(int(eid) if eid is not None else None),
            )
            btn.pack(fill="x", padx=8, pady=2)
        self.request_resize()

    def _refresh_vendors_panel(self, vendors: List[Dict[str, Any]]) -> None:
        if not self._vendors_frame:
            return
        self._clear_frame(self._vendors_frame)
        if not vendors:
            ctk.CTkLabel(self._vendors_frame, text="Нет магазинов", text_color="#6b7280").pack(
                anchor="w", padx=8, pady=8,
            )
            return
        for vendor in vendors[:15]:
            stock = "пусто" if vendor.get("out_of_stock") else "в наличии"
            orders = vendor.get("sell_orders", [])
            order_hint = ""
            if orders:
                first = orders[0]
                order_hint = f" | item {first.get('item_id')} x{first.get('quantity')} за {first.get('cost_per_item')}"
            ctk.CTkLabel(
                self._vendors_frame,
                text=f"{vendor.get('name', 'Магазин')} [{vendor.get('grid', '?')}] — {stock}{order_hint}",
                anchor="w", font=ctk.CTkFont(size=10), text_color="#d1d7e3",
            ).pack(fill="x", padx=8, pady=2)
        self.request_resize()

    def _search_vendors(self) -> None:
        query = self._vendor_search.get() if self._vendor_search else ""
        filtered = filter_vendors(self._vendors_cache, query)
        self._refresh_vendors_panel(filtered)

    def _refresh_devices_panel(self) -> None:
        if not self._devices_frame:
            return
        self._clear_frame(self._devices_frame)
        server = self._service.connection.connected_server
        if not server:
            ctk.CTkLabel(
                self._devices_frame,
                text="Спарьте устройство в игре (Pair) при активном listener",
                text_color="#6b7280",
            ).pack(anchor="w", padx=8, pady=8)
            return

        devices = self._service.store.list_devices(server.id)
        if not devices:
            ctk.CTkLabel(
                self._devices_frame,
                text="Нет устройств. В игре: Pair на Smart Switch / Alarm / Storage",
                text_color="#6b7280",
            ).pack(anchor="w", padx=8, pady=8)
            return

        for device in devices:
            row = ctk.CTkFrame(self._devices_frame, fg_color="#1a2030", corner_radius=4)
            row.pack(fill="x", padx=4, pady=2)
            state = self._device_states.get(device.entity_id, {})
            if device.device_type == "smart_switch":
                status = "ВКЛ" if state.get("value") else "ВЫКЛ"
            elif device.device_type == "smart_alarm":
                status = "🚨 ТРЕВОГА" if state.get("value") else "ок"
            elif device.device_type == "storage_monitor":
                items = state.get("items", "?")
                cap = state.get("capacity", "?")
                expiry = state.get("protection_expiry")
                has_prot = state.get("has_protection")
                hours = upkeep_hours_left(expiry, self._server_time_raw) if has_prot else None
                if hours is not None:
                    if hours < 1:
                        status = f"{items}/{cap} | upkeep {hours * 60:.0f}м 🟥"
                    elif hours < 6:
                        status = f"{items}/{cap} | upkeep {hours:.1f}ч 🟨"
                    else:
                        status = f"{items}/{cap} | upkeep {hours:.1f}ч 🟩"
                else:
                    status = f"{items}/{cap}"
            else:
                status = "тревога" if state.get("value") else "ок"

            color = "#f87171" if device.device_type == "smart_alarm" and state.get("value") else "#d1d7e3"
            ctk.CTkLabel(
                row,
                text=f"{device.name} ({device.device_type}) — {status}",
                anchor="w", font=ctk.CTkFont(size=10), text_color=color,
            ).pack(side="left", padx=8, pady=6)

            if device.device_type == "smart_switch":
                ctk.CTkButton(
                    row, text="ON", width=40, height=24, fg_color="#2a5a2a",
                    command=lambda eid=device.entity_id: self._service.toggle_device(eid, True),
                ).pack(side="right", padx=2)
                ctk.CTkButton(
                    row, text="OFF", width=40, height=24, fg_color="#4a2230",
                    command=lambda eid=device.entity_id: self._service.toggle_device(eid, False),
                ).pack(side="right", padx=2)
            ctk.CTkButton(
                row, text="✕", width=28, height=24, fg_color="#3d4659",
                command=lambda did=device.id: self._remove_device(did),
            ).pack(side="right", padx=4)
        self.request_resize()

    def _remove_device(self, device_id: str) -> None:
        self._service.store.remove_device(device_id)
        self._refresh_devices_panel()

    def _open_camera_from_input(self) -> None:
        if not self._camera_input:
            return
        camera_id = self._camera_input.get().strip()
        if not camera_id:
            self._set_status("Введите ID камеры", error=True)
            return
        self._open_camera_view(camera_id)

    def _save_camera_from_input(self) -> None:
        if not self._camera_input:
            return
        camera_id = self._camera_input.get().strip()
        if not camera_id:
            self._set_status("Введите ID камеры", error=True)
            return
        self._service.add_camera(camera_id)
        self._refresh_cameras_panel()

    def _open_camera_view(self, camera_id: str) -> None:
        if not self._service.connection.is_connected:
            self._set_status("Сначала подключитесь к серверу", error=True)
            return
        if self._camera_window and self._camera_window.is_open:
            self._camera_window.close()
            self._camera_window = None
        self._service.open_camera(camera_id)

    def _close_camera_window(self) -> None:
        if self._camera_window and self._camera_window.is_open:
            self._camera_window.close()
        self._camera_window = None

    def _refresh_cameras_panel(self) -> None:
        if not self._cameras_frame:
            return
        self._clear_frame(self._cameras_frame)
        server = self._service.get_active_server()
        if not server:
            ctk.CTkLabel(
                self._cameras_frame, text="Нет активного сервера", text_color="#6b7280",
            ).pack(anchor="w", padx=8, pady=8)
            return

        cameras = self._service.store.list_cameras(server.id)
        if not cameras:
            ctk.CTkLabel(
                self._cameras_frame,
                text="Нет сохранённых камер",
                text_color="#6b7280",
            ).pack(anchor="w", padx=8, pady=8)
            return

        for camera in cameras:
            row = ctk.CTkFrame(self._cameras_frame, fg_color="#1a2030", corner_radius=4)
            row.pack(fill="x", padx=4, pady=2)
            ctk.CTkLabel(
                row,
                text=f"{camera.name} ({camera.camera_id})",
                anchor="w", font=ctk.CTkFont(size=10), text_color="#d1d7e3",
            ).pack(side="left", padx=8, pady=6)
            ctk.CTkButton(
                row, text="Открыть", width=70, height=24, fg_color="#c45c26",
                command=lambda cid=camera.camera_id: self._open_camera_view(cid),
            ).pack(side="right", padx=4, pady=4)
            ctk.CTkButton(
                row, text="✕", width=32, height=24, fg_color="#4a2230",
                command=lambda dbid=camera.id: self._remove_camera(dbid),
            ).pack(side="right", padx=4, pady=4)
        self.request_resize()

    def _remove_camera(self, camera_db_id: str) -> None:
        self._service.remove_camera(camera_db_id)
        self._refresh_cameras_panel()

    def _toggle_minimap(self) -> None:
        if not self._map_path:
            self._set_status("Сначала загрузите карту", error=True)
            return
        shown = self._minimap.toggle(self._map_path)
        if shown:
            self._minimap.set_team(self._team_cache, self._map_size)
            self._set_status("Миникарта: перетаскивайте ЛКМ, скрыть — ПКМ")
        else:
            self._set_status("Миникарта скрыта")

    def _open_map_window(self) -> None:
        if not self._map_path:
            self._set_status("Сначала загрузите карту", error=True)
            return
        if self._map_window and self._map_window.is_open:
            self._map_window.lift()
            return
        self._map_window = MapWindow(
            self._root,
            self._map_path,
            map_size=self._map_size,
            team_members=self._team_cache,
            death_markers=self._map_overlay_deaths(
                self._service.get_active_server().id if self._service.get_active_server() else None
            ),
            drawings=[d.to_dict() for d in self._service.store.list_map_drawings(
                self._service.get_active_server().id if self._service.get_active_server() else None
            )],
            events=self._map_overlay_events(),
            vendors=self._map_overlay_vendors(),
            tracked_event_id=self._service.store.get_tracked_event_id(),
            follow_steam_id=self._service.store.get_follow_steam_id(),
            on_close=self._clear_map_window,
            on_track_event=self._track_event,
            on_add_drawing=self._add_map_drawing,
            renderer=self._service.map_renderer,
        )

    def _clear_map_window(self) -> None:
        self._map_window = None

    def _append_alert(self, message: str, category: str = "") -> None:
        from datetime import datetime

        alerts = self._service.store.get_alert_settings()
        allowed = {
            "cargo": alerts.cargo,
            "death": alerts.death,
            "shop": alerts.shop,
            "alarm": alerts.alarm,
        }
        if category and category in allowed and not allowed[category]:
            return

        stamp = datetime.now().strftime("%H:%M")
        line = f"[{stamp}] {message}"
        self._alerts_log.insert(0, line)
        self._alerts_log = self._alerts_log[:12]
        self._refresh_alerts_panel()
        self._overlay.show_live_alert(message)

    def _refresh_alerts_panel(self) -> None:
        if not self._alerts_frame:
            return
        self._clear_frame(self._alerts_frame)
        if not self._alerts_log:
            ctk.CTkLabel(
                self._alerts_frame,
                text="Пока нет уведомлений",
                text_color="#6b7280",
            ).pack(anchor="w", padx=8, pady=8)
            return
        for line in self._alerts_log:
            ctk.CTkLabel(
                self._alerts_frame,
                text=line,
                anchor="w",
                font=ctk.CTkFont(size=10),
                text_color="#fbbf24",
            ).pack(fill="x", padx=8, pady=2)
        self.request_resize()

    def _show_map_preview(self, path: str) -> None:
        if not self._map_preview:
            return
        self._map_path = path
        try:
            image = Image.open(path)
            image.thumbnail(self.MAP_PREVIEW_MAX, Image.Resampling.LANCZOS)
            self._map_image_ref = ctk.CTkImage(
                light_image=image, dark_image=image, size=image.size,
            )
            self._map_preview.configure(image=self._map_image_ref, text="")
            self._minimap.update(path, self._team_cache, self._map_size)
            self._sync_map_overlays()
        except Exception:
            self._map_preview.configure(text="Не удалось показать карту")
        self.request_resize()

    def on_hide(self) -> None:
        if self._poll_job:
            self._root.after_cancel(self._poll_job)
            self._poll_job = None

    def on_shutdown(self) -> None:
        if self._map_window and self._map_window.is_open:
            self._map_window.close()
        self._map_window = None
        self._close_camera_window()
        self._minimap.destroy()

    def _status_text(self) -> str:
        return self._service.store.fcm_expiry_warning() or ""

    def _refresh_status(self) -> None:
        fcm = self._service.fcm
        if self._status_pills:
            set_pill(self._status_pills["FCM"], "FCM", fcm.has_config())
            set_pill(
                self._status_pills["Node"],
                "Node",
                fcm.runtime_ready(),
                "" if fcm.runtime_ready() else " setup",
            )
            set_pill(self._status_pills["Listener"], "Listener", fcm.is_listening)
            set_pill(
                self._status_pills["Сервер"],
                "Сервер",
                self._service.connection.is_connected,
            )
        warn = self._service.store.fcm_expiry_warning()
        if self._status_label:
            self._status_label.configure(text=warn or "", text_color=Theme.WARN if warn else Theme.DIM)

    def _register_fcm(self, browser: str = "auto") -> None:
        ok, msg = self._service.fcm.register(browser=browser)
        self._set_status(msg, error=not ok)
        self._refresh_status()

    def _reset_fcm(self) -> None:
        self._service.fcm.stop_listen()
        self._service.fcm.reset_config()
        self._refresh_status()
        self._set_status("FCM config сброшен. Зарегистрируйтесь заново.")

    def _start_listener(self) -> None:
        ok, msg = self._service.fcm.start_listen()
        self._set_status(msg, error=not ok)
        self._refresh_status()

    def _stop_listener(self) -> None:
        self._service.fcm.stop_listen()
        self._refresh_status()

    def _servers_block_height(self, count: int) -> int:
        if count <= 0:
            return 36
        visible = min(count, self.SERVERS_MAX_VISIBLE)
        return visible * self.SERVER_ROW_HEIGHT + max(0, visible - 1) * 2 + 8

    def _apply_servers_block_height(self, count: int) -> None:
        height = self._servers_block_height(count)
        if self._servers_frame:
            self._servers_frame.configure(height=height)
        if getattr(self, "_servers_outer", None):
            self._servers_outer.configure(height=height)
            self._servers_outer.pack_propagate(False)

    def _refresh_servers(self) -> None:
        if not self._servers_frame:
            return
        self._service.store.load()
        for w in self._servers_frame.winfo_children():
            w.destroy()

        servers = self._service.store.list_servers()
        self._apply_servers_block_height(len(servers))
        if not servers:
            ctk.CTkLabel(
                self._servers_frame,
                text="Нет серверов. Запустите listener и нажмите Pair Server в Rust+.",
                text_color=Theme.DIM,
                font=ctk.CTkFont(size=10),
            ).pack(anchor="w", padx=8, pady=8)
        else:
            for server in servers:
                self._server_row(server)
        self.request_resize()

    def _server_row(self, server: PairedServer) -> None:
        assert self._servers_frame is not None
        active = self._service.connection.connected_server
        is_active = bool(active and active.id == server.id)
        border = Theme.SUCCESS if is_active else Theme.BORDER

        row = ctk.CTkFrame(
            self._servers_frame,
            fg_color=Theme.CARD_ALT,
            corner_radius=8,
            height=self.SERVER_ROW_HEIGHT,
            border_width=1,
            border_color=border,
        )
        row.pack(fill="x", pady=1)
        row.pack_propagate(False)

        actions = ctk.CTkFrame(row, fg_color="transparent", width=112)
        actions.pack(side="right", padx=6, pady=6)
        actions.pack_propagate(False)
        btn_danger(
            actions, "✕", lambda sid=server.id: self._remove_server(sid), width=28, height=28,
        ).pack(side="right", padx=(4, 0))
        if is_active:
            ctk.CTkLabel(
                actions,
                text="Online",
                font=ctk.CTkFont(size=9, weight="bold"),
                text_color=Theme.SUCCESS,
                width=52,
            ).pack(side="right", padx=(0, 4))
        else:
            btn_secondary(
                actions, "Connect", lambda s=server: self._connect(s), width=72, height=28,
            ).pack(side="right")

        mark = "● " if is_active else ""
        display_name = server.name if len(server.name) <= 34 else server.name[:31] + "..."
        ctk.CTkLabel(
            row,
            text=(
                f"{mark}{display_name}\n"
                f"{server.ip}:{server.port}  ·  token ...{str(server.player_token)[-4:]}"
            ),
            anchor="w",
            justify="left",
            wraplength=300,
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT,
        ).pack(side="left", fill="both", expand=True, padx=10, pady=6)

    def _add_manual_server(self) -> None:
        ip = self._manual_ip.get().strip() if self._manual_ip else ""
        try:
            port = int(self._manual_port.get().strip())
            player_id = int(self._manual_player_id.get().strip())
            player_token = int(self._manual_token.get().strip())
        except ValueError:
            self._set_status("Заполните IP, порт, Steam ID и Token числами", error=True)
            return
        if not ip:
            self._set_status("Укажите IP сервера", error=True)
            return
        name = self._manual_name.get().strip() if self._manual_name else "Server"
        self._service.store.add_server(name, ip, port, player_id, player_token)
        self._refresh_servers()
        self._set_status(f"Сервер {name} добавлен вручную")

    def _connect(self, server: PairedServer) -> None:
        self._service.connect_server(server)
        self._set_status(f"Подключение к {server.name}...")

    def _remove_server(self, server_id: str) -> None:
        name = self._service.store.get_server(server_id)
        self._service.remove_server(server_id)
        self._refresh_servers()
        self._refresh_status()
        self._refresh_devices_panel()
        self._refresh_cameras_panel()
        removed = name.name if name else "сервер"
        self._set_status(f"Удалён: {removed}")

    def _send_chat(self) -> None:
        if not self._chat_input:
            return
        text = self._chat_input.get().strip()
        if not text:
            return
        self._service.connection.send_team_message(text)
        self._chat_input.delete(0, "end")

    def _set_status(self, message: str, error: bool = False) -> None:
        if self._status_label:
            color = Theme.ERROR if error else Theme.TEXT
            self._status_label.configure(text=message, text_color=color)
        self._refresh_status()

    def _start_event_pump(self) -> None:
        def pump():
            self._service.event_bus.dispatch_all_pending()
            self._poll_job = self._root.after(200, pump)
        self._poll_job = self._root.after(200, pump)

    def _on_event(self, event: RustPlusEvent) -> None:
        def apply():
            if event.type == EventType.STATUS:
                self._set_status(str(event.payload.get("message", "")))
                self._refresh_status()
            elif event.type == EventType.ERROR:
                self._set_status(str(event.payload.get("message", "Ошибка")), error=True)
            elif event.type == EventType.SERVER_PAIRED:
                self._refresh_servers()
            elif event.type == EventType.CONNECTED:
                self._refresh_servers()
                self._refresh_status()
                self._refresh_devices_panel()
                self._service.refresh_device_states()
                if self._info_label:
                    self._info_label.configure(text=f"Подключено: {event.payload.get('name', '')}")
                self._set_status(f"Подключено к {event.payload.get('name', '')}")
            elif event.type == EventType.DISCONNECTED:
                self._refresh_status()
                self._vendors_cache = []
                self._device_states = {}
                self._server_time = ""
                self._map_path = None
                self._map_size = None
                self._team_cache = []
                self._minimap.hide()
                self._close_camera_window()
                self._alerts_log = []
                self._refresh_alerts_panel()
                self._refresh_team_panel([])
                self._refresh_events_panel([])
                self._refresh_vendors_panel([])
                self._refresh_devices_panel()
                if self._info_label:
                    self._info_label.configure(text="Не подключено")
            elif event.type == EventType.SERVER_INFO:
                map_size = event.payload.get("map_size")
                if map_size:
                    self._map_size = int(map_size)
                    self._minimap.set_team(self._team_cache, self._map_size)
                if self._info_label:
                    players = event.payload.get("players")
                    max_p = event.payload.get("max_players")
                    name = event.payload.get("name", "")
                    map_name = event.payload.get("map_name")
                    warning = event.payload.get("warning")
                    if players is not None and max_p is not None:
                        players_text = f"Игроков: {players}/{max_p}"
                    else:
                        players_text = "Игроки: данные недоступны"
                    text = f"{name}\n{players_text}"
                    if map_name:
                        text += f"\nКарта: {map_name}"
                    if self._server_time:
                        text += f"\nВремя: {self._server_time}"
                    if warning:
                        text += f"\n{warning}"
                    self._info_label.configure(text=text)
            elif event.type == EventType.SERVER_TIME:
                self._server_time_raw = event.payload.get("raw_time")
                self._server_time = str(event.payload.get("time", ""))
                if self._info_label and self._service.connection.is_connected:
                    current = self._info_label.cget("text")
                    lines = [line for line in current.split("\n") if not line.startswith("Время:")]
                    lines.append(f"Время: {self._server_time}")
                    self._info_label.configure(text="\n".join(lines))
            elif event.type == EventType.TEAM_INFO:
                self._team_cache = event.payload.get("members", [])
                self._refresh_team_panel(self._team_cache)
                self._sync_map_overlays()
            elif event.type == EventType.MARKERS:
                self._vendors_cache = event.payload.get("vendors", [])
                self._events_cache = event.payload.get("events", [])
                self._refresh_events_panel(self._events_cache)
                query = self._vendor_search.get().strip() if self._vendor_search else ""
                vendors = filter_vendors(self._vendors_cache, query) if query else self._vendors_cache
                self._refresh_vendors_panel(vendors)
                self._sync_map_overlays()
            elif event.type == EventType.ENTITY_CHANGED:
                entity_id = int(event.payload.get("entity_id", 0))
                self._device_states[entity_id] = {
                    "value": event.payload.get("value"),
                    "capacity": event.payload.get("capacity"),
                    "items": event.payload.get("items"),
                    "has_protection": event.payload.get("has_protection"),
                    "protection_expiry": event.payload.get("protection_expiry"),
                }
                self._refresh_devices_panel()
            elif event.type == EventType.MAP_IMAGE:
                path = event.payload.get("path")
                if path:
                    self._show_map_preview(str(path))
                    self._sync_map_overlays()
            elif event.type == EventType.LIVE_ALERT:
                self._append_alert(
                    str(event.payload.get("message", "Событие на сервере")),
                    category=str(event.payload.get("category", "")),
                )
            elif event.type == EventType.DEVICE_PAIRED:
                self._refresh_devices_panel()
            elif event.type == EventType.CHAT_MESSAGE:
                self._append_chat(
                    event.payload.get("name", "?"),
                    event.payload.get("message", ""),
                )
            elif event.type == EventType.CAMERA_STATUS:
                if event.payload.get("open"):
                    cam_id = str(event.payload.get("camera_id", ""))
                    if self._camera_window and self._camera_window.is_open:
                        self._camera_window.close()
                    self._camera_window = CameraWindow(
                        self._root,
                        self._service,
                        cam_id,
                        controls={
                            "movement": bool(event.payload.get("movement")),
                            "mouse": bool(event.payload.get("mouse")),
                        },
                    )
                else:
                    self._close_camera_window()
            elif event.type == EventType.CAMERA_FRAME:
                path = event.payload.get("path")
                if path and self._camera_window and self._camera_window.is_open:
                    self._camera_window.update_frame(str(path))
            self.request_resize()

        self._root.after(0, apply)

    def _append_chat(self, name: str, message: str) -> None:
        if not self._chat_frame:
            return
        ctk.CTkLabel(
            self._chat_frame,
            text=f"{name}: {message}",
            anchor="w",
            font=ctk.CTkFont(size=11),
            text_color="#d1d7e3",
        ).pack(fill="x", padx=8, pady=2)
        children = self._chat_frame.winfo_children()
        if len(children) > 30:
            children[0].destroy()
