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
    settings_group,
    set_pill,
    status_pill,
    step_card,
    field_label,
)
from features.rustplus_hub.camera_window import CameraWindow
from features.rustplus_hub.map_window import MapWindow
from features.rustplus_hub.minimap_window import MinimapWindow
from overlay.key_capture import KeyCapture
from overlay.hotkey_util import hotkey_label
from services.rustplus.event_bus import EventType, RustPlusEvent
from services.rustplus.live_format import (
    build_vendor_item_catalog,
    classify_vendor,
    collect_item_offers,
    filter_vendor_catalog_items,
    filter_vendors_by_kind,
    upkeep_hours_left,
    vendors_state_signature,
)
from services.rustplus.service import RustPlusService
from storage.rustplus_store import AlertSettings, MapLayerSettings, PairedServer

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
    VENDOR_PAGE_SIZE = 20
    VENDOR_ITEM_PAGE_SIZE = 30
    VENDOR_OFFER_PAGE_SIZE = 20
    MAX_VENDOR_ORDERS = 3
    VENDOR_REFRESH_DEBOUNCE_MS = 500
    MAP_SYNC_DEBOUNCE_MS = 900

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
        self._key_capture = KeyCapture(overlay.root)
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
        self._vendor_kind_var = ctk.StringVar(value="all")
        self._vendors_count_label: Optional[ctk.CTkLabel] = None
        self._vendor_page_label: Optional[ctk.CTkLabel] = None
        self._vendor_watch_btn: Optional[ctk.CTkButton] = None
        self._vendor_page = 0
        self._vendor_view_mode = "catalog"
        self._vendor_selected_item_id: Optional[int] = None
        self._vendor_catalog_cache: List[Dict[str, Any]] = []
        self._vendor_filtered_catalog: List[Dict[str, Any]] = []
        self._vendor_offers_cache: List[Dict[str, Any]] = []
        self._vendors_render_job: Optional[str] = None
        self._map_sync_job: Optional[str] = None
        self._event_dock_job: Optional[str] = None
        self._vendors_signature: Optional[str] = None
        self._map_overlay_signature: Optional[str] = None
        self._map_preview: Optional[ctk.CTkLabel] = None
        self._map_image_ref: Optional[ctk.CTkImage] = None
        self._vendors_cache: List[Dict[str, Any]] = []
        self._vendor_icon_refs: List[ctk.CTkImage] = []
        self._vendor_icon_labels: Dict[int, ctk.CTkLabel] = {}
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
            command=self._on_tab_changed,
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
        self._start_event_dock_refresh()
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
        self._section_title(parent, "Магазины", "Выберите товар — покажем лавки, цену и остаток")
        filter_row = ctk.CTkFrame(parent, fg_color="transparent")
        filter_row.pack(fill="x", padx=4, pady=(0, 6))
        for kind, label in [("all", "Все"), ("player", "Игроки"), ("monument", "Монументы")]:
            btn_secondary(
                filter_row,
                label,
                lambda k=kind: self._set_vendor_kind(k),
                width=88,
                height=28,
            ).pack(side="left", padx=(0, 4))
        self._vendors_count_label = ctk.CTkLabel(
            filter_row,
            text="",
            font=ctk.CTkFont(size=10),
            text_color=Theme.DIM,
        )
        self._vendors_count_label.pack(side="right", padx=(8, 0))

        search_row = ctk.CTkFrame(parent, fg_color="transparent")
        search_row.pack(fill="x", padx=4, pady=(0, 6))
        self._vendor_search = ctk.StringVar()
        entry = ctk.CTkEntry(
            search_row,
            textvariable=self._vendor_search,
            placeholder_text="Поиск товара",
            height=30,
            corner_radius=8,
        )
        entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        entry.bind("<Return>", lambda _e: self._search_vendor_items())
        entry.bind("<KeyRelease>", lambda _e: self._on_vendor_item_search_change())
        btn_secondary(search_row, "Найти", self._search_vendor_items, width=72, height=30).pack(side="left")

        nav_row = ctk.CTkFrame(parent, fg_color="transparent")
        nav_row.pack(fill="x", padx=4, pady=(0, 6))
        self._vendor_prev_btn = btn_secondary(nav_row, "←", self._vendor_prev_page, width=36, height=28)
        self._vendor_back_btn = btn_secondary(
            nav_row, "← Товары", self._show_vendor_catalog, width=88, height=28,
        )
        self._vendor_watch_btn = btn_secondary(
            nav_row, "★ Следить", self._toggle_vendor_watch, width=96, height=28,
        )
        self._vendor_prev_btn.pack(side="left")
        self._vendor_page_label = ctk.CTkLabel(
            nav_row,
            text="стр. 1/1",
            font=ctk.CTkFont(size=10),
            text_color=Theme.DIM,
        )
        self._vendor_page_label.pack(side="left", padx=8)
        btn_secondary(nav_row, "→", self._vendor_next_page, width=36, height=28).pack(side="left")

        self._vendor_selected_label = ctk.CTkLabel(
            parent,
            text="",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=Theme.TEXT,
            anchor="w",
        )
        self._vendor_selected_label.pack(fill="x", padx=8, pady=(0, 4))

        self._vendors_frame = panel(parent)
        self._vendors_frame.pack(fill="x", padx=4, pady=(0, 8))
        ctk.CTkLabel(
            self._vendors_frame, text="Нет товаров в наличии", text_color=Theme.DIM,
        ).pack(anchor="w", padx=10, pady=10)

    def _build_devices_section(self, parent: ctk.CTkScrollableFrame) -> None:
        section_header(
            parent,
            "Умные устройства",
            "Switch, Alarm, Storage Monitor",
            action_text="Обновить",
            action_command=self._refresh_devices_action,
        )
        self._devices_frame = panel(parent)
        self._devices_frame.pack(fill="x", padx=4, pady=(0, 8))
        self._refresh_devices_panel()

    def _refresh_devices_action(self) -> None:
        """Подтянуть пропущенные Pair из лога + опросить состояние."""
        server = self._service.get_active_server() or self._service.connection.connected_server
        server_id = server.id if server else None
        added = self._service.store.sync_devices_from_pairing_log(server_id)
        if self._service.connection.is_connected:
            self._service.connection.refresh_devices()
            self._service.refresh_device_states()
        self._refresh_devices_panel()
        self._refresh_groups_label()
        if added:
            self._set_status(f"Добавлено устройств из pairing: {added}")
        else:
            self._set_status("Устройства обновлены")

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

        layers = self._service.store.get_map_layers()
        self._map_layer_vars = {
            "monuments": ctk.BooleanVar(value=layers.monuments),
            "players": ctk.BooleanVar(value=layers.players),
            "shops": ctk.BooleanVar(value=layers.shops),
        }
        layers_card = panel(parent)
        layers_card.pack(fill="x", padx=4, pady=(0, 8))
        field_label(layers_card, "Слои на карте")
        layer_hints = {
            "monuments": "Монументы и POI на базовой карте",
            "players": "Позиции команды на карте и оверлее",
            "shops": "Вендинги и бродячие торговцы",
        }
        for key, label in [
            ("monuments", "Монументы"),
            ("players", "Игроки"),
            ("shops", "Магазины"),
        ]:
            layer_row = ctk.CTkFrame(layers_card, fg_color="transparent")
            layer_row.pack(fill="x", padx=10, pady=2)
            ctk.CTkCheckBox(
                layer_row,
                text=label,
                variable=self._map_layer_vars[key],
                width=110,
                command=self._save_map_layers,
            ).pack(side="left")
            ctk.CTkLabel(
                layer_row,
                text=layer_hints[key],
                font=ctk.CTkFont(size=10),
                text_color=Theme.DIM,
                anchor="w",
            ).pack(side="left", padx=(8, 0))
        hint_label(layers_card, "Слои применяются сразу к миникарте и большой карте.")

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
        self._section_title(
            parent,
            "Настройки",
            "Сгруппировано по смыслу — меняйте только нужный блок",
        )

        alerts = self._service.store.get_alert_settings()
        self._alert_vars = {
            "cargo": ctk.BooleanVar(value=alerts.cargo),
            "death": ctk.BooleanVar(value=alerts.death),
            "shop": ctk.BooleanVar(value=alerts.shop),
            "alarm": ctk.BooleanVar(value=alerts.alarm),
            "spawn_patrol": ctk.BooleanVar(value=alerts.spawn_patrol),
            "spawn_chinook": ctk.BooleanVar(value=alerts.spawn_chinook),
            "spawn_cargo": ctk.BooleanVar(value=alerts.spawn_cargo),
            "spawn_vendor": ctk.BooleanVar(value=alerts.spawn_vendor),
            "cargo_arrival": ctk.BooleanVar(value=alerts.cargo_arrival),
            "cargo_docking": ctk.BooleanVar(value=alerts.cargo_docking),
            "cargo_departure": ctk.BooleanVar(value=alerts.cargo_departure),
        }
        alerts_body = settings_group(
            parent,
            "Уведомления и карта",
            "Снятая галочка убирает toast и алерты (магазины на карте — во вкладке «Карта»).",
        )
        alert_hints = {
            "cargo": "Карго, верт, chinook — события и алерты",
            "death": "Смерти тиммейтов + маркеры на карте",
            "shop": "Алерты о выгодных сделках и изменениях шопов",
            "alarm": "Smart Alarm (FCM и в игре)",
            "spawn_patrol": "Team chat: спавн патрульного вертолёта",
            "spawn_chinook": "Team chat: спавн Chinook",
            "spawn_cargo": "Team chat: появление Cargo Ship",
            "spawn_vendor": "Team chat: появление бродячего торговца",
            "cargo_arrival": "Cargo intel: первое появление/сектор",
            "cargo_docking": "Cargo intel: постановка в порт",
            "cargo_departure": "Cargo intel: предупреждение перед отходом",
        }
        for key, label in [
            ("cargo", "Карго"), ("death", "Смерть"), ("shop", "Магазины"), ("alarm", "Alarm"),
            ("spawn_patrol", "Spawn: Верт"),
            ("spawn_chinook", "Spawn: Chinook"),
            ("spawn_cargo", "Spawn: Cargo"),
            ("spawn_vendor", "Spawn: Vendor"),
            ("cargo_arrival", "Cargo: Arrival"),
            ("cargo_docking", "Cargo: Docking"),
            ("cargo_departure", "Cargo: Departure"),
        ]:
            row = ctk.CTkFrame(alerts_body, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkCheckBox(
                row,
                text=label,
                variable=self._alert_vars[key],
                width=100,
                command=self._save_alert_settings,
            ).pack(side="left")
            ctk.CTkLabel(
                row,
                text=alert_hints[key],
                font=ctk.CTkFont(size=10),
                text_color=Theme.DIM,
                anchor="w",
            ).pack(side="left", padx=(8, 0))

        settings = self._service.store.get_settings()
        app_body = settings_group(
            parent,
            "Приложение",
            "Фоновая работа и команды в team chat от вашего ника.",
        )
        self._autostart_var = ctk.BooleanVar(value=settings.autostart)
        self._tray_var = ctk.BooleanVar(value=settings.minimize_to_tray)
        self._chat_cmd_var = ctk.BooleanVar(value=settings.chat_commands_enabled)
        for text, var, tip in [
            ("Запускать с Windows", self._autostart_var, "Оверлей стартует при входе в систему"),
            ("Сворачивать в tray", self._tray_var, "F6 — выход; иконка в трее — показать снова"),
            ("Чат-команды", self._chat_cmd_var, "!on / !off / !toggle / !leader / !upkeep / !mark"),
        ]:
            row = ctk.CTkFrame(app_body, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkCheckBox(
                row, text=text, variable=var, command=self._save_app_settings,
            ).pack(side="left")
            ctk.CTkLabel(
                row, text=tip, font=ctk.CTkFont(size=10), text_color=Theme.DIM, anchor="w",
            ).pack(side="left", padx=(8, 0))

        map_body = settings_group(
            parent,
            "Карта",
            "Следование камеры и очистка маркеров смерти.",
        )
        field_label(map_body, "Smart Follow — Steam ID игрока")
        follow_row = ctk.CTkFrame(map_body, fg_color="transparent")
        follow_row.pack(fill="x", pady=(0, 6))
        self._follow_var = ctk.StringVar(value="")
        ctk.CTkEntry(
            follow_row,
            textvariable=self._follow_var,
            width=200,
            height=30,
            placeholder_text="76561198…",
            corner_radius=8,
        ).pack(side="left", padx=(0, 6))
        btn_secondary(follow_row, "Применить", self._save_follow, width=90, height=30).pack(side="left")
        hint_label(map_body, "Миникарта и большая карта центрируются на этом игроке.")
        btn_secondary(
            map_body, "Очистить маркеры смерти", self._clear_deaths, width=180, height=28,
        ).pack(anchor="w", pady=(4, 0))

        devices_body = settings_group(
            parent,
            "Устройства и горячие клавиши",
            "Выберите Switch галочками — видно, что попадёт в группу. Hotkey на один Switch или на группу.",
        )
        share_row = ctk.CTkFrame(devices_body, fg_color="transparent")
        share_row.pack(fill="x", pady=(0, 8))
        btn_secondary(share_row, "Экспорт в буфер", self._export_devices, width=120, height=28).pack(side="left", padx=(0, 6))
        btn_secondary(share_row, "Импорт", self._import_devices_dialog, width=80, height=28).pack(side="left")
        hint_label(devices_body, "В чате: !share и !import — или вставьте base64 вручную.")

        field_label(devices_body, "Выбор Switch")
        pick_actions = ctk.CTkFrame(devices_body, fg_color="transparent")
        pick_actions.pack(fill="x", pady=(0, 4))
        btn_secondary(pick_actions, "Все", self._select_all_switches, width=60, height=26).pack(side="left", padx=(0, 6))
        btn_secondary(pick_actions, "Сбросить", self._clear_switch_selection, width=80, height=26).pack(side="left")
        self._switch_pick_frame = ctk.CTkScrollableFrame(
            devices_body, fg_color=Theme.CARD_ALT, height=110, corner_radius=8,
        )
        self._switch_pick_frame.pack(fill="x", pady=(0, 4))
        self._selection_summary = ctk.CTkLabel(
            devices_body,
            text="Ничего не выбрано",
            font=ctk.CTkFont(size=11),
            text_color=Theme.MUTED,
            anchor="w",
            justify="left",
            wraplength=480,
        )
        self._selection_summary.pack(fill="x", pady=(0, 8))

        field_label(devices_body, "Группа из выбранных")
        group_row = ctk.CTkFrame(devices_body, fg_color="transparent")
        group_row.pack(fill="x", pady=(0, 8))
        self._group_name_var = ctk.StringVar(value="Группа")
        ctk.CTkEntry(
            group_row, textvariable=self._group_name_var, width=120, height=28,
            placeholder_text="Название", corner_radius=8,
        ).pack(side="left", padx=(0, 6))
        btn_secondary(
            group_row, "Создать группу", self._create_switch_group, width=120, height=28,
        ).pack(side="left")

        field_label(devices_body, "Горячая клавиша")
        hotkey_row = ctk.CTkFrame(devices_body, fg_color="transparent")
        hotkey_row.pack(fill="x", pady=(0, 4))
        self._hotkey_action_var = ctk.StringVar(value="toggle")
        ctk.CTkOptionMenu(
            hotkey_row,
            variable=self._hotkey_action_var,
            values=["toggle", "on", "off"],
            width=90,
            height=28,
        ).pack(side="left", padx=(0, 6))
        btn_primary(
            hotkey_row, "Забиндить выбранные", self._bind_hotkey_to_selection, width=150, height=28,
        ).pack(side="left", padx=(0, 6))
        hint_label(
            devices_body,
            "Нажмите кнопку бинда → затем нужную клавишу на клавиатуре. Esc — отмена. "
            "1 Switch → на него; несколько → группа. У группы/Switch кнопка ⌨ — то же самое.",
        )

        field_label(devices_body, "Группы и привязки")
        self._groups_list_frame = ctk.CTkFrame(devices_body, fg_color="transparent")
        self._groups_list_frame.pack(fill="x", pady=(0, 4))
        self._hotkeys_list_frame = ctk.CTkFrame(devices_body, fg_color="transparent")
        self._hotkeys_list_frame.pack(fill="x", pady=(4, 0))
        self._switch_check_vars: Dict[str, ctk.BooleanVar] = {}
        self._refresh_switch_picker()
        self._refresh_groups_label()

        shop_body = settings_group(
            parent,
            "Аналитика магазинов",
            "Поиск выгодных сделок между вендингами на текущем сервере.",
        )
        field_label(shop_body, "Частота опроса Rust+")
        poll_row = ctk.CTkFrame(shop_body, fg_color="transparent")
        poll_row.pack(fill="x", pady=(0, 6))
        self._poll_interval_var = ctk.StringVar(value=str(settings.poll_interval_sec))
        ctk.CTkOptionMenu(
            poll_row,
            variable=self._poll_interval_var,
            values=["5", "8", "10", "15", "20"],
            width=90,
            height=28,
            command=lambda _value: self._save_poll_interval(),
        ).pack(side="left")
        ctk.CTkLabel(
            poll_row,
            text="сек · команда, карта, магазины",
            font=ctk.CTkFont(size=10),
            text_color=Theme.DIM,
            anchor="w",
        ).pack(side="left", padx=(8, 0))
        hint_label(
            shop_body,
            "5 с — быстрее всего. 20 с — щадящий режим. Слишком частый опрос может упереться в лимиты Rust+.",
        )
        field_label(shop_body, "Item ID для расчёта profit")
        profit_row = ctk.CTkFrame(shop_body, fg_color="transparent")
        profit_row.pack(fill="x")
        self._profit_item_var = ctk.StringVar(value="")
        ctk.CTkEntry(
            profit_row, textvariable=self._profit_item_var, width=100, height=28,
            placeholder_text="напр. -151838493", corner_radius=8,
        ).pack(side="left", padx=(0, 6))
        btn_secondary(profit_row, "Найти маршрут", self._show_profit, width=110, height=28).pack(side="left")
        self._profit_label = ctk.CTkLabel(
            shop_body, text="", font=ctk.CTkFont(size=10), text_color=Theme.MUTED, anchor="w", wraplength=500,
        )
        self._profit_label.pack(fill="x", pady=(6, 0))

        cross_body = settings_group(
            parent,
            "Прицел поверх игры",
            "Отдельное прозрачное окно — не мешает Rust+ Live.",
        )
        self._crosshair_var = ctk.BooleanVar(value=settings.crosshair_enabled)
        ctk.CTkCheckBox(
            cross_body, text="Показывать прицел", variable=self._crosshair_var, command=self._save_crosshair,
        ).pack(anchor="w", pady=(0, 6))
        field_label(cross_body, "Размер · цвет (#hex)")
        params = ctk.CTkFrame(cross_body, fg_color="transparent")
        params.pack(fill="x")
        self._cross_size_var = ctk.StringVar(value=str(settings.crosshair_size))
        self._cross_color_var = ctk.StringVar(value=settings.crosshair_color)
        ctk.CTkEntry(params, textvariable=self._cross_size_var, width=50, height=28, corner_radius=8).pack(side="left", padx=(0, 6))
        ctk.CTkEntry(params, textvariable=self._cross_color_var, width=80, height=28, placeholder_text="#00ff00", corner_radius=8).pack(side="left", padx=(0, 6))
        btn_secondary(params, "Сохранить", self._save_crosshair, width=90, height=28).pack(side="left")

        sound_body = settings_group(
            parent,
            "Звук Smart Alarm",
            "Путь к .wav файлу на диске. Пусто — системный сигнал Windows.",
        )
        self._alarm_sound_var = ctk.StringVar(value=settings.alarm_sound_path)
        sound_row = ctk.CTkFrame(sound_body, fg_color="transparent")
        sound_row.pack(fill="x")
        ctk.CTkEntry(
            sound_row,
            textvariable=self._alarm_sound_var,
            height=30,
            placeholder_text="C:\\Sounds\\alarm.wav",
            corner_radius=8,
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))
        btn_secondary(sound_row, "Сохранить", self._save_alarm_sound, width=90, height=30).pack(side="left")

        intel_body = settings_group(
            parent,
            "Player Intelligence",
            "Локальная статистика онлайна без Battlemetrics. Нужно несколько сессий для данных.",
        )
        intel_row = ctk.CTkFrame(intel_body, fg_color="transparent")
        intel_row.pack(fill="x")
        btn_secondary(
            intel_row, "Показать прогноз", self._show_player_intel, width=130, height=28,
        ).pack(side="left")
        self._intel_label = ctk.CTkLabel(
            intel_body,
            text="Укажите Steam ID в блоке «Карта» или дождитесь данных по команде",
            font=ctk.CTkFont(size=10),
            text_color=Theme.DIM,
            anchor="w",
            wraplength=500,
        )
        self._intel_label.pack(fill="x", pady=(8, 0))

        warn_card = card(parent, alt=True)
        warn_card.pack(fill="x", padx=4, pady=(0, 8))
        ctk.CTkLabel(
            warn_card,
            text="FCM и pairing",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=Theme.MUTED,
        ).pack(anchor="w", padx=12, pady=(10, 4))
        self._fcm_warn_label = ctk.CTkLabel(
            warn_card,
            text="",
            font=ctk.CTkFont(size=10),
            text_color=Theme.WARN,
            anchor="w",
            wraplength=520,
        )
        self._fcm_warn_label.pack(fill="x", padx=12, pady=(0, 12))
        self._refresh_fcm_warning()
        self._refresh_groups_label()

    def _save_alert_settings(self) -> None:
        alerts = AlertSettings(
            cargo=self._alert_vars["cargo"].get(),
            death=self._alert_vars["death"].get(),
            shop=self._alert_vars["shop"].get(),
            alarm=self._alert_vars["alarm"].get(),
            spawn_patrol=self._alert_vars["spawn_patrol"].get(),
            spawn_chinook=self._alert_vars["spawn_chinook"].get(),
            spawn_cargo=self._alert_vars["spawn_cargo"].get(),
            spawn_vendor=self._alert_vars["spawn_vendor"].get(),
            cargo_arrival=self._alert_vars["cargo_arrival"].get(),
            cargo_docking=self._alert_vars["cargo_docking"].get(),
            cargo_departure=self._alert_vars["cargo_departure"].get(),
        )
        self._service.update_alert_settings(alerts)
        self._map_overlay_signature = None
        self._schedule_map_overlay_sync()
        if self._service.connection.is_connected:
            self._service.fetch_map()

    def _save_map_layers(self) -> None:
        layers = MapLayerSettings(
            monuments=self._map_layer_vars["monuments"].get(),
            players=self._map_layer_vars["players"].get(),
            shops=self._map_layer_vars["shops"].get(),
        )
        self._service.update_map_layers(layers)
        self._map_overlay_signature = None
        self._schedule_map_overlay_sync()
        if self._service.connection.is_connected:
            self._service.fetch_map()

    def _map_overlay_team(self) -> List[Dict[str, Any]]:
        if not self._service.store.get_map_layers().players:
            return []
        return self._team_cache

    def _map_overlay_vendors(self) -> List[Dict[str, Any]]:
        if not self._service.store.get_map_layers().shops:
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

    def _save_poll_interval(self) -> None:
        try:
            interval = int(self._poll_interval_var.get())
        except ValueError:
            interval = 10
        interval = max(5, min(20, interval))
        self._poll_interval_var.set(str(interval))
        settings = self._service.store.get_settings()
        settings.poll_interval_sec = interval
        self._service.update_app_settings(settings)

    def _save_follow(self) -> None:
        raw = self._follow_var.get().strip()
        steam_id = int(raw) if raw.isdigit() else None
        self._service.store.set_follow_steam_id(steam_id)
        self._map_overlay_signature = None
        self._schedule_map_overlay_sync()

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
        self._refresh_groups_label()
        self._set_status(f"Импортировано устройств: {count}")

    def _clear_deaths(self) -> None:
        server = self._service.get_active_server()
        self._service.store.clear_death_markers(server.id if server else None)
        self._map_overlay_signature = None
        self._schedule_map_overlay_sync()

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
            text=(
                f"+{first['profit_percent']}% · x{first['final_amount']} · "
                f"{first['hops']} шага | {first['route']}"
            ),
        )

    def _create_switch_group(self) -> None:
        server = self._service.get_active_server()
        if not server:
            self._set_status("Нет активного сервера", error=True)
            return
        selected = self._selected_switches()
        if not selected:
            self._set_status("Отметьте хотя бы один Switch", error=True)
            return
        name = self._group_name_var.get().strip() or "Группа"
        group = self._service.store.add_device_group(
            server.id, name, [d.id for d in selected],
        )
        names = ", ".join(d.name for d in selected)
        self._set_status(f"Группа «{group.name}»: {names}")
        self._refresh_groups_label()

    def _normalize_captured_hotkey(self, hotkey: str) -> Optional[str]:
        hotkey = (hotkey or "").strip().lower()
        if not hotkey:
            return None
        reserved_names = {"f5", "f6"}
        reserved_scans: set[int] = set()
        try:
            import keyboard
            for name in reserved_names:
                reserved_scans.update(keyboard.key_to_scan_codes(name, False) or ())
        except Exception:
            reserved_scans.update({63, 64})  # типичные scancode F5/F6
        for part in hotkey.split("+"):
            part = part.strip()
            if part in reserved_names:
                self._set_status(f"Клавиша {part.upper()} зарезервирована (оверлей)", error=True)
                return None
            if part.startswith("sc:"):
                try:
                    scan = int(part[3:])
                except ValueError:
                    continue
                if scan in reserved_scans:
                    self._set_status(f"Клавиша {hotkey_label(hotkey)} зарезервирована (оверлей)", error=True)
                    return None
        return hotkey

    def _capture_hotkey(
        self,
        *,
        prompt: str,
        on_hotkey,
    ) -> None:
        if self._key_capture.is_active:
            return
        self._set_status("Ожидание клавиши…")
        # чтобы случайно не сработали уже привязанные device hotkeys во время захвата
        self._service.unload_device_hotkeys()

        def on_captured(raw: str) -> None:
            self._service.reload_device_hotkeys()
            hotkey = self._normalize_captured_hotkey(raw)
            if not hotkey:
                return
            on_hotkey(hotkey)

        def on_cancel() -> None:
            self._service.reload_device_hotkeys()
            self._set_status("Привязка отменена")

        self._key_capture.capture(on_captured, on_cancel=on_cancel, prompt=prompt)

    def _bind_hotkey_to_selection(self) -> None:
        selected = self._selected_switches()
        if not selected:
            self._set_status("Отметьте Switch для hotkey", error=True)
            return
        names = ", ".join(d.name for d in selected)
        self._capture_hotkey(
            prompt=f"Клавиша для:\n{names}",
            on_hotkey=lambda hk: self._apply_hotkey_to_selection(hk, selected),
        )

    def _apply_hotkey_to_selection(self, hotkey: str, selected) -> None:
        action = self._hotkey_action_var.get().strip().lower() or "toggle"
        try:
            if len(selected) == 1:
                device = selected[0]
                self._service.store.add_device_hotkey(
                    hotkey, device_id=device.id, action=action,
                )
                target = device.name
            else:
                server = self._service.get_active_server()
                if not server:
                    self._set_status("Нет активного сервера", error=True)
                    return
                name = self._group_name_var.get().strip() or f"Группа {hotkey.upper()}"
                group = self._service.store.add_device_group(
                    server.id, name, [d.id for d in selected],
                )
                self._service.store.add_device_hotkey(
                    hotkey, group_id=group.id, action=action,
                )
                target = f"{group.name} ({', '.join(d.name for d in selected)})"
        except ValueError as exc:
            self._set_status(str(exc), error=True)
            return
        self._service.reload_device_hotkeys()
        self._set_status(f"{hotkey_label(hotkey)} → {action} → {target}")
        self._refresh_groups_label()
        self._refresh_devices_panel()

    def _bind_hotkey_to_group_id(self, group_id: str, group_name: str) -> None:
        self._capture_hotkey(
            prompt=f"Клавиша для группы «{group_name}»",
            on_hotkey=lambda hk: self._apply_hotkey_to_group(hk, group_id, group_name),
        )

    def _apply_hotkey_to_group(self, hotkey: str, group_id: str, group_name: str) -> None:
        action = self._hotkey_action_var.get().strip().lower() or "toggle"
        try:
            self._service.store.add_device_hotkey(
                hotkey, group_id=group_id, action=action,
            )
        except ValueError as exc:
            self._set_status(str(exc), error=True)
            return
        self._service.reload_device_hotkeys()
        group = next((g for g in self._service.store.list_device_groups() if g.id == group_id), None)
        members = self._group_member_names(group) if group else "?"
        self._set_status(f"{hotkey_label(hotkey)} → {group_name}: {members}")
        self._refresh_groups_label()
        self._refresh_devices_panel()

    def _bind_device_hotkey_dialog(self, device_id: str, device_name: str) -> None:
        self._capture_hotkey(
            prompt=f"Клавиша для Switch «{device_name}»",
            on_hotkey=lambda hk: self._apply_hotkey_to_device(hk, device_id, device_name),
        )

    def _apply_hotkey_to_device(self, hotkey: str, device_id: str, device_name: str) -> None:
        try:
            self._service.store.add_device_hotkey(
                hotkey, device_id=device_id, action="toggle",
            )
        except ValueError as exc:
            self._set_status(str(exc), error=True)
            return
        self._service.reload_device_hotkeys()
        self._set_status(f"{hotkey_label(hotkey)} → toggle → {device_name}")
        self._refresh_groups_label()
        self._refresh_devices_panel()

    def _selected_switches(self):
        server = self._service.get_active_server()
        if not server:
            return []
        devices = [
            d for d in self._service.store.list_devices(server.id)
            if d.device_type == "smart_switch"
        ]
        return [d for d in devices if self._switch_check_vars.get(d.id) and self._switch_check_vars[d.id].get()]

    def _select_all_switches(self) -> None:
        for var in self._switch_check_vars.values():
            var.set(True)
        self._update_selection_summary()

    def _clear_switch_selection(self) -> None:
        for var in self._switch_check_vars.values():
            var.set(False)
        self._update_selection_summary()

    def _update_selection_summary(self) -> None:
        if not hasattr(self, "_selection_summary"):
            return
        selected = self._selected_switches()
        if not selected:
            self._selection_summary.configure(text="Ничего не выбрано")
            return
        names = ", ".join(d.name for d in selected)
        self._selection_summary.configure(
            text=f"В группу / hotkey попадёт ({len(selected)}): {names}",
        )

    def _refresh_switch_picker(self) -> None:
        if not hasattr(self, "_switch_pick_frame") or self._switch_pick_frame is None:
            return
        for child in self._switch_pick_frame.winfo_children():
            child.destroy()
        prev = {did: var.get() for did, var in getattr(self, "_switch_check_vars", {}).items()}
        self._switch_check_vars = {}
        server = self._service.get_active_server()
        if not server:
            ctk.CTkLabel(
                self._switch_pick_frame,
                text="Подключитесь к серверу",
                text_color=Theme.DIM,
                font=ctk.CTkFont(size=11),
            ).pack(anchor="w", padx=8, pady=8)
            self._update_selection_summary()
            return
        switches = [
            d for d in self._service.store.list_devices(server.id)
            if d.device_type == "smart_switch"
        ]
        if not switches:
            ctk.CTkLabel(
                self._switch_pick_frame,
                text="Нет Smart Switch. Спарьте устройство в игре.",
                text_color=Theme.DIM,
                font=ctk.CTkFont(size=11),
            ).pack(anchor="w", padx=8, pady=8)
            self._update_selection_summary()
            return
        for device in switches:
            var = ctk.BooleanVar(value=bool(prev.get(device.id, False)))
            self._switch_check_vars[device.id] = var
            ctk.CTkCheckBox(
                self._switch_pick_frame,
                text=device.name,
                variable=var,
                command=self._update_selection_summary,
                font=ctk.CTkFont(size=12),
            ).pack(anchor="w", padx=8, pady=2)
        self._update_selection_summary()

    def _group_member_names(self, group) -> str:
        by_id = {d.id: d.name for d in self._service.store.list_devices(group.server_id)}
        names = [by_id.get(did, "?") for did in group.device_ids]
        return ", ".join(names) if names else "пусто"

    def _refresh_groups_label(self) -> None:
        self._refresh_switch_picker()
        if hasattr(self, "_groups_list_frame") and self._groups_list_frame is not None:
            for child in self._groups_list_frame.winfo_children():
                child.destroy()
            server = self._service.get_active_server()
            groups = self._service.store.list_device_groups(server.id if server else None)
            if not groups:
                ctk.CTkLabel(
                    self._groups_list_frame,
                    text="Групп пока нет",
                    font=ctk.CTkFont(size=10),
                    text_color=Theme.DIM,
                    anchor="w",
                ).pack(fill="x")
            else:
                for group in groups:
                    row = ctk.CTkFrame(self._groups_list_frame, fg_color=Theme.CARD_ALT, corner_radius=6)
                    row.pack(fill="x", pady=2)
                    members = self._group_member_names(group)
                    ctk.CTkLabel(
                        row,
                        text=f"📦 {group.name}: {members}",
                        font=ctk.CTkFont(size=11),
                        text_color=Theme.TEXT,
                        anchor="w",
                        wraplength=420,
                        justify="left",
                    ).pack(side="left", padx=8, pady=6, fill="x", expand=True)
                    ctk.CTkButton(
                        row, text="⌨", width=28, height=24, fg_color="#3d4659",
                        command=lambda gid=group.id, gname=group.name: self._bind_hotkey_to_group_id(gid, gname),
                    ).pack(side="right", padx=2, pady=4)
                    ctk.CTkButton(
                        row, text="✕", width=28, height=24, fg_color="#3d4659",
                        command=lambda gid=group.id: self._delete_device_group(gid),
                    ).pack(side="right", padx=6, pady=4)

        if hasattr(self, "_hotkeys_list_frame") and self._hotkeys_list_frame is not None:
            for child in self._hotkeys_list_frame.winfo_children():
                child.destroy()
            hotkeys = self._service.store.list_device_hotkeys()
            if not hotkeys:
                ctk.CTkLabel(
                    self._hotkeys_list_frame,
                    text="Hotkey не привязаны",
                    font=ctk.CTkFont(size=10),
                    text_color=Theme.DIM,
                    anchor="w",
                ).pack(fill="x")
                return
            devices = {d.id: d for d in self._service.store.list_devices()}
            groups = {g.id: g for g in self._service.store.list_device_groups()}
            for entry in hotkeys:
                if entry.device_id and entry.device_id in devices:
                    target = f"Switch «{devices[entry.device_id].name}»"
                elif entry.group_id and entry.group_id in groups:
                    group = groups[entry.group_id]
                    target = f"группа «{group.name}» ({self._group_member_names(group)})"
                else:
                    target = "не найдено"
                row = ctk.CTkFrame(self._hotkeys_list_frame, fg_color=Theme.CARD_ALT, corner_radius=6)
                row.pack(fill="x", pady=2)
                ctk.CTkLabel(
                    row,
                    text=f"⌨ {hotkey_label(entry.hotkey)} · {entry.action} → {target}",
                    font=ctk.CTkFont(size=11),
                    text_color=Theme.TEXT,
                    anchor="w",
                    wraplength=420,
                    justify="left",
                ).pack(side="left", padx=8, pady=6, fill="x", expand=True)
                ctk.CTkButton(
                    row, text="✕", width=28, height=24, fg_color="#3d4659",
                    command=lambda hid=entry.id: self._delete_device_hotkey(hid),
                ).pack(side="right", padx=6, pady=4)

    def _delete_device_group(self, group_id: str) -> None:
        self._service.store.remove_device_group(group_id)
        self._service.reload_device_hotkeys()
        self._set_status("Группа удалена")
        self._refresh_groups_label()
        self._refresh_devices_panel()

    def _delete_device_hotkey(self, hotkey_id: str) -> None:
        self._service.store.remove_device_hotkey(hotkey_id)
        self._service.reload_device_hotkeys()
        self._set_status("Hotkey удалён")
        self._refresh_groups_label()
        self._refresh_devices_panel()

    def _refresh_fcm_warning(self) -> None:
        if hasattr(self, "_fcm_warn_label"):
            warn = self._service.store.fcm_expiry_warning()
            self._fcm_warn_label.configure(text=warn or "")

    def _is_map_tab_active(self) -> bool:
        try:
            return self._tabs.get().strip() == "Карта"
        except Exception:
            return False

    def _on_tab_changed(self) -> None:
        if self._is_map_tab_active():
            self._apply_vendor_filters(render_panel=True)

    def _schedule_vendor_refresh(self, *, force: bool = False) -> None:
        if self._vendors_render_job:
            self._root.after_cancel(self._vendors_render_job)

        def run() -> None:
            self._vendors_render_job = None
            signature = vendors_state_signature(self._vendors_cache)
            if not force and signature == self._vendors_signature:
                self._update_vendors_count_meta()
                return
            self._vendors_signature = signature
            self._apply_vendor_filters(render_panel=self._is_map_tab_active() or force)

        self._vendors_render_job = self._root.after(self.VENDOR_REFRESH_DEBOUNCE_MS, run)

    def _schedule_map_overlay_sync(self) -> None:
        if self._map_sync_job:
            self._root.after_cancel(self._map_sync_job)

        def run() -> None:
            self._map_sync_job = None
            signature = self._map_overlay_data_signature()
            if signature == self._map_overlay_signature:
                return
            self._map_overlay_signature = signature
            self._sync_map_overlays()

        self._map_sync_job = self._root.after(self.MAP_SYNC_DEBOUNCE_MS, run)

    def _map_overlay_data_signature(self) -> str:
        server = self._service.get_active_server()
        server_id = server.id if server else None
        team = self._map_overlay_team()
        team_bits = [
            f"{m.get('steam_id')}:{int(bool(m.get('is_online')))}:{m.get('x')}:{m.get('y')}"
            for m in team[:16]
        ]
        return "|".join([
            str(server_id),
            str(self._map_size),
            str(len(self._vendors_cache)),
            str(len(self._events_cache)),
            str(self._service.store.get_follow_steam_id()),
            str(self._service.store.get_tracked_event_id()),
            ",".join(team_bits),
        ])

    def _sync_map_overlays(self) -> None:
        server = self._service.get_active_server()
        server_id = server.id if server else None
        state = {
            "members": self._map_overlay_team(),
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
        self._map_overlay_signature = None
        self._refresh_events_panel(self._events_cache)
        self._schedule_map_overlay_sync()
        if event_id:
            self._set_status(f"Трекинг события #{event_id} на карте")

    def _add_map_drawing(self, x: float, y: float, text: str) -> None:
        server = self._service.get_active_server()
        if not server:
            return
        self._service.store.add_map_drawing(server.id, x, y, text)
        self._map_overlay_signature = None
        self._schedule_map_overlay_sync()

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
        tracked_event_id = self._service.store.get_tracked_event_id()
        for event in events[:8]:
            eid = event.get("id")
            cargo_status = event.get("cargo_status") or {}
            is_tracked = eid is not None and int(eid) == int(tracked_event_id or 0)
            card = ctk.CTkFrame(
                self._events_frame,
                fg_color="#20293b" if is_tracked else "#1a2030",
                corner_radius=8,
            )
            card.pack(fill="x", padx=8, pady=3)

            head = ctk.CTkFrame(card, fg_color="transparent")
            head.pack(fill="x", padx=8, pady=(6, 2))
            ctk.CTkLabel(
                head,
                text=f"{event.get('type_name', '?')} [{event.get('grid', '?')}]",
                anchor="w",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=Theme.TEXT,
            ).pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(
                head,
                text="TRACK" if is_tracked else "TRACK",
                font=ctk.CTkFont(size=9, weight="bold"),
                text_color=Theme.INFO if is_tracked else Theme.MUTED,
            ).pack(side="right")

            badges = self._event_dock_badges(event)
            if badges:
                meta = ctk.CTkFrame(card, fg_color="transparent")
                meta.pack(fill="x", padx=8, pady=(0, 2))
                for text, color in badges:
                    ctk.CTkLabel(
                        meta,
                        text=text,
                        font=ctk.CTkFont(size=9, weight="bold"),
                        text_color=color,
                        fg_color=Theme.CARD_ALT,
                        corner_radius=6,
                        padx=6,
                        pady=2,
                    ).pack(side="left", padx=(0, 4))

            ctk.CTkButton(
                card,
                text="Трек на карте",
                height=26,
                fg_color="#243149",
                hover_color="#2d3b55",
                font=ctk.CTkFont(size=10),
                command=lambda eid=eid: self._track_event(int(eid) if eid is not None else None),
            ).pack(anchor="e", padx=8, pady=(2, 6))
        self.request_resize()

    def _event_dock_badges(self, event: Dict[str, Any]) -> List[tuple[str, str]]:
        badges: List[tuple[str, str]] = []
        cargo_status = event.get("cargo_status") or {}
        if cargo_status:
            remaining = cargo_status.get("remaining_minutes")
            if cargo_status.get("in_harbor") and remaining is not None:
                badges.append((f"порт {remaining} мин", Theme.WARN))
            route = cargo_status.get("route") or []
            if route:
                badges.append((f"route {' -> '.join(route[-2:])}", Theme.INFO))
        event_name = str(event.get("type_name", "")).lower()
        if "chinook" in event_name:
            badges.append(("air", Theme.INFO))
        elif "верт" in event_name:
            badges.append(("heli", Theme.WARN))
        elif "карго" in event_name:
            badges.append(("sea", Theme.SUCCESS))
        elif "торгов" in event_name:
            badges.append(("vendor", Theme.MUTED))
        return badges

    def _start_event_dock_refresh(self) -> None:
        if self._event_dock_job:
            return

        def tick():
            self._event_dock_job = None
            if self._events_cache:
                self._refresh_events_panel(self._events_cache)
            self._start_event_dock_refresh()

        self._event_dock_job = self._root.after(1000, tick)

    def _refresh_vendors_panel(self) -> None:
        if not self._vendors_frame:
            return
        self._clear_frame(self._vendors_frame)
        self._vendor_icon_refs.clear()
        self._vendor_icon_labels.clear()

        if self._vendor_view_mode == "offers":
            self._refresh_vendor_offers_panel()
        else:
            self._refresh_vendor_catalog_panel()
        self._update_vendors_count_meta()

    def _refresh_vendor_catalog_panel(self) -> None:
        if not self._vendors_frame:
            return
        items = self._current_vendor_catalog_page()
        if not items:
            ctk.CTkLabel(
                self._vendors_frame,
                text="Нет товаров в наличии",
                text_color=Theme.DIM,
            ).pack(anchor="w", padx=8, pady=8)
            return

        icons = self._service.item_icons
        icon_size = 24
        for item in items:
            row = ctk.CTkFrame(self._vendors_frame, fg_color=Theme.CARD_ALT, corner_radius=8, cursor="hand2")
            row.pack(fill="x", padx=8, pady=2)
            row.bind("<Button-1>", lambda _e, iid=int(item["item_id"]): self._select_vendor_item(iid))

            item_icon = ctk.CTkLabel(
                row,
                text="",
                width=icon_size,
                height=icon_size,
                fg_color="transparent",
            )
            item_icon.pack(side="left", padx=(8, 6), pady=6)
            item_icon.bind("<Button-1>", lambda _e, iid=int(item["item_id"]): self._select_vendor_item(iid))
            self._queue_item_icon(item_icon, int(item["item_id"]), icon_size, icons)

            min_cost = int(item.get("min_cost", 0))
            currency_name = icons.item_name(int(item.get("min_currency_id", 0)))
            meta = f"{item.get('shop_count', 0)} лавок · от {min_cost} {currency_name}"
            label = ctk.CTkLabel(
                row,
                text=f"{item.get('name', 'Товар')}  ·  {meta}",
                anchor="w",
                font=ctk.CTkFont(size=11),
                text_color=Theme.TEXT,
            )
            label.pack(side="left", fill="x", expand=True, pady=6, padx=(0, 8))
            label.bind("<Button-1>", lambda _e, iid=int(item["item_id"]): self._select_vendor_item(iid))

    def _refresh_vendor_offers_panel(self) -> None:
        if not self._vendors_frame or self._vendor_selected_item_id is None:
            return
        offers = self._current_vendor_offers_page()
        if not offers:
            ctk.CTkLabel(
                self._vendors_frame,
                text="Нет предложений по выбранному товару",
                text_color=Theme.DIM,
            ).pack(anchor="w", padx=8, pady=8)
            return

        icons = self._service.item_icons
        icon_size = 24
        kind_labels = {
            "player": ("Игрок", Theme.INFO),
            "monument": ("Монумент", Theme.MUTED),
            "traveling": ("Бродяга", Theme.WARN),
        }
        for offer in offers:
            vendor = offer["vendor"]
            order = offer["order"]
            card = ctk.CTkFrame(self._vendors_frame, fg_color="#1a2030", corner_radius=8)
            card.pack(fill="x", padx=8, pady=4)

            kind = classify_vendor(vendor)
            kind_text, kind_color = kind_labels.get(kind, ("Магазин", Theme.MUTED))
            head = ctk.CTkFrame(card, fg_color="transparent")
            head.pack(fill="x", padx=8, pady=(8, 4))
            ctk.CTkLabel(
                head,
                text=f"{vendor.get('name', 'Магазин')} [{vendor.get('grid', '?')}]",
                anchor="w",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=Theme.TEXT,
            ).pack(side="left")
            ctk.CTkLabel(
                head,
                text=kind_text,
                font=ctk.CTkFont(size=9, weight="bold"),
                text_color=kind_color,
                fg_color=Theme.CARD_ALT,
                corner_radius=6,
                padx=6,
                pady=2,
            ).pack(side="right", padx=(6, 0))

            self._build_vendor_order_row(card, order, icon_size, icons)

    def _select_vendor_item(self, item_id: int) -> None:
        self._vendor_selected_item_id = int(item_id)
        self._vendor_view_mode = "offers"
        self._vendor_page = 0
        self._vendor_offers_cache = collect_item_offers(
            self._filtered_vendors_for_catalog(),
            self._vendor_selected_item_id,
        )
        if self._vendor_back_btn and self._vendor_prev_btn:
            self._vendor_back_btn.pack(side="left", padx=(0, 6), before=self._vendor_prev_btn)
        icons = self._service.item_icons
        if self._vendor_selected_label:
            self._vendor_selected_label.configure(
                text=icons.item_name(self._vendor_selected_item_id),
            )
        self._refresh_vendor_watch_button()
        self._refresh_vendors_panel()

    def _show_vendor_catalog(self) -> None:
        self._vendor_view_mode = "catalog"
        self._vendor_selected_item_id = None
        self._vendor_page = 0
        self._vendor_offers_cache = []
        if self._vendor_back_btn:
            self._vendor_back_btn.pack_forget()
        if self._vendor_selected_label:
            self._vendor_selected_label.configure(text="")
        if self._vendor_watch_btn:
            self._vendor_watch_btn.pack_forget()
        self._refresh_vendors_panel()

    def _refresh_vendor_watch_button(self) -> None:
        if not self._vendor_watch_btn or self._vendor_selected_item_id is None or not self._vendor_prev_btn:
            return
        watched = set(self._service.list_shop_watch_items())
        if self._vendor_selected_item_id in watched:
            self._vendor_watch_btn.configure(text="☆ Не следить")
        else:
            self._vendor_watch_btn.configure(text="★ Следить")
        self._vendor_watch_btn.pack(side="left", padx=(0, 6), before=self._vendor_prev_btn)

    def _toggle_vendor_watch(self) -> None:
        if self._vendor_selected_item_id is None:
            return
        item_id = int(self._vendor_selected_item_id)
        watched = set(self._service.list_shop_watch_items())
        item_name = self._service.item_icons.item_name(item_id)
        if item_id in watched:
            self._service.remove_shop_watch_item(item_id)
            self._set_status(f"Watchlist: удалён {item_name}")
        else:
            self._service.add_shop_watch_item(item_id)
            self._set_status(f"Watchlist: добавлен {item_name}")
        if self._vendor_selected_label:
            self._vendor_selected_label.configure(text=item_name)
        self._refresh_vendor_watch_button()

    def _build_vendor_order_row(
        self,
        parent: ctk.CTkFrame,
        order: Dict[str, Any],
        icon_size: int,
        icons,
    ) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=2)

        item_id = int(order.get("item_id", 0))
        currency_id = int(order.get("currency_id", 0))
        qty = int(order.get("quantity", 0))
        cost = int(order.get("cost_per_item", 0))
        stock = int(order.get("amount_in_stock", 0))

        item_icon = ctk.CTkLabel(
            row,
            text="",
            width=icon_size,
            height=icon_size,
            fg_color=Theme.CARD_ALT,
            corner_radius=6,
        )
        item_icon.pack(side="left")
        self._queue_item_icon(item_icon, item_id, icon_size, icons)

        ctk.CTkLabel(
            row,
            text=f"×{qty}",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=Theme.TEXT,
            width=34,
        ).pack(side="left", padx=(4, 2))

        ctk.CTkLabel(
            row,
            text="→",
            font=ctk.CTkFont(size=12),
            text_color=Theme.MUTED,
            width=16,
        ).pack(side="left")

        currency_icon = ctk.CTkLabel(
            row,
            text="",
            width=icon_size,
            height=icon_size,
            fg_color=Theme.CARD_ALT,
            corner_radius=6,
        )
        currency_icon.pack(side="left", padx=(2, 0))
        self._queue_item_icon(currency_icon, currency_id, icon_size, icons)

        ctk.CTkLabel(
            row,
            text=f"×{cost}",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=Theme.ACCENT,
            width=40,
        ).pack(side="left", padx=(4, 0))

        hint = f"остаток {stock}" if stock else icons.item_name(item_id)
        ctk.CTkLabel(
            row,
            text=hint,
            font=ctk.CTkFont(size=10),
            text_color=Theme.DIM,
            anchor="w",
        ).pack(side="left", padx=(8, 0))

    def _queue_item_icon(
        self,
        label: ctk.CTkLabel,
        item_id: int,
        icon_size: int,
        icons,
    ) -> None:
        item_id = int(item_id)
        image = icons.get(item_id)
        if image:
            self._apply_item_icon(label, image, icon_size)
            return

        fallback = icons.fallback_glyph(item_id)
        label.configure(text=fallback, font=ctk.CTkFont(size=10, weight="bold"), text_color=Theme.MUTED)

        def on_ready(iid: int, pil_image: Image.Image) -> None:
            if not label.winfo_exists():
                return
            self._root.after(0, lambda: self._apply_item_icon(label, pil_image, icon_size))

        icons.fetch_async(item_id, on_ready)

    def _apply_item_icon(self, label: ctk.CTkLabel, image: Image.Image, icon_size: int) -> None:
        if not label.winfo_exists():
            return
        thumb = image.copy()
        thumb.thumbnail((icon_size, icon_size), Image.Resampling.LANCZOS)
        ctk_image = ctk.CTkImage(light_image=thumb, dark_image=thumb, size=(icon_size, icon_size))
        self._vendor_icon_refs.append(ctk_image)
        label.configure(image=ctk_image, text="")

    def _set_vendor_kind(self, kind: str) -> None:
        self._vendor_kind_var.set(kind)
        self._vendor_page = 0
        if self._vendor_view_mode == "offers" and self._vendor_selected_item_id is not None:
            self._vendor_offers_cache = collect_item_offers(
                self._filtered_vendors_for_catalog(),
                self._vendor_selected_item_id,
            )
        self._apply_vendor_filters(render_panel=True)

    def _vendor_prev_page(self) -> None:
        if self._vendor_page > 0:
            self._vendor_page -= 1
            self._refresh_vendors_panel()

    def _vendor_next_page(self) -> None:
        if self._vendor_view_mode == "offers":
            items = self._vendor_offers_cache
            page_size = self.VENDOR_OFFER_PAGE_SIZE
        else:
            items = self._vendor_filtered_catalog or self._rebuild_vendor_catalog()
            page_size = self.VENDOR_ITEM_PAGE_SIZE
        total_pages = max(1, (len(items) + page_size - 1) // page_size)
        if self._vendor_page < total_pages - 1:
            self._vendor_page += 1
            self._refresh_vendors_panel()

    def _filtered_vendors_for_catalog(self) -> List[Dict[str, Any]]:
        return filter_vendors_by_kind(self._vendors_cache, self._vendor_kind_var.get())

    def _rebuild_vendor_catalog(self) -> List[Dict[str, Any]]:
        vendors = self._filtered_vendors_for_catalog()
        self._vendor_catalog_cache = build_vendor_item_catalog(
            vendors,
            item_name_fn=self._service.item_icons.item_name,
            in_stock_only=True,
        )
        query = self._vendor_search.get().strip() if self._vendor_search else ""
        self._vendor_filtered_catalog = filter_vendor_catalog_items(self._vendor_catalog_cache, query)
        return self._vendor_filtered_catalog

    def _current_vendor_catalog_page(self) -> List[Dict[str, Any]]:
        items = self._vendor_filtered_catalog or self._rebuild_vendor_catalog()
        start = self._vendor_page * self.VENDOR_ITEM_PAGE_SIZE
        return items[start:start + self.VENDOR_ITEM_PAGE_SIZE]

    def _current_vendor_offers_page(self) -> List[Dict[str, Any]]:
        offers = self._vendor_offers_cache
        start = self._vendor_page * self.VENDOR_OFFER_PAGE_SIZE
        return offers[start:start + self.VENDOR_OFFER_PAGE_SIZE]

    def _apply_vendor_filters(self, *, render_panel: bool = True) -> None:
        self._rebuild_vendor_catalog()
        if self._vendor_view_mode == "offers" and self._vendor_selected_item_id is not None:
            self._vendor_offers_cache = collect_item_offers(
                self._filtered_vendors_for_catalog(),
                self._vendor_selected_item_id,
            )
        if render_panel:
            self._refresh_vendors_panel()
        else:
            self._update_vendors_count_meta()

    def _update_vendors_count_meta(self) -> None:
        if not self._vendors_count_label:
            return
        total_vendors = self._vendors_cache
        if self._vendor_view_mode == "offers":
            items = self._vendor_offers_cache
            page_size = self.VENDOR_OFFER_PAGE_SIZE
            label_prefix = "предложений"
        else:
            items = self._vendor_filtered_catalog or self._rebuild_vendor_catalog()
            page_size = self.VENDOR_ITEM_PAGE_SIZE
            label_prefix = "товаров"

        total_pages = max(1, (len(items) + page_size - 1) // page_size)
        if self._vendor_page >= total_pages:
            self._vendor_page = 0
        shown_from = self._vendor_page * page_size + 1 if items else 0
        shown_to = min((self._vendor_page + 1) * page_size, len(items))
        catalog_size = len(self._vendor_catalog_cache)
        if not catalog_size and self._vendors_cache:
            catalog_size = len(self._rebuild_vendor_catalog())
        self._vendors_count_label.configure(
            text=(
                f"{label_prefix} {shown_from}-{shown_to} из {len(items)}"
                f" · в каталоге {catalog_size}"
                f" · лавок {len(total_vendors)}"
            ),
        )
        if self._vendor_page_label:
            self._vendor_page_label.configure(text=f"стр. {self._vendor_page + 1}/{total_pages}")

    def _search_vendor_items(self) -> None:
        self._vendor_page = 0
        if self._vendor_view_mode == "catalog":
            self._apply_vendor_filters(render_panel=True)
        else:
            self._show_vendor_catalog()
            self._apply_vendor_filters(render_panel=True)

    def _on_vendor_item_search_change(self) -> None:
        if self._vendor_view_mode != "catalog":
            return
        if self._vendors_render_job:
            self._root.after_cancel(self._vendors_render_job)

        def run() -> None:
            self._vendors_render_job = None
            self._vendor_page = 0
            self._apply_vendor_filters(render_panel=True)

        self._vendors_render_job = self._root.after(250, run)

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

        hotkey_by_device = self._device_hotkey_hints(server.id)

        for device in devices:
            row = ctk.CTkFrame(self._devices_frame, fg_color="#1a2030", corner_radius=4)
            row.pack(fill="x", padx=4, pady=2)
            state = self._device_states.get(device.entity_id, {})
            if device.device_type == "smart_switch":
                is_on = bool(state.get("value"))
                status = "ВКЛ" if is_on else "ВЫКЛ"
            elif device.device_type == "smart_alarm":
                is_on = False
                status = "🚨 ТРЕВОГА" if state.get("value") else "ок"
            elif device.device_type == "storage_monitor":
                is_on = False
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
                is_on = False
                status = "тревога" if state.get("value") else "ок"

            color = "#f87171" if device.device_type == "smart_alarm" and state.get("value") else "#d1d7e3"
            name_wrap = ctk.CTkFrame(row, fg_color="transparent")
            name_wrap.pack(side="left", fill="x", expand=True, padx=8, pady=4)
            if device.device_type == "smart_switch":
                label_text = device.name
            else:
                label_text = f"{device.name} — {status}"
            ctk.CTkLabel(
                name_wrap,
                text=label_text,
                anchor="w", font=ctk.CTkFont(size=12), text_color=color,
            ).pack(side="left")
            hint = hotkey_by_device.get(device.id)
            if hint:
                ctk.CTkLabel(
                    name_wrap,
                    text=f"  [{hint}]",
                    anchor="w",
                    font=ctk.CTkFont(size=11, weight="bold"),
                    text_color="#e07a3a",
                ).pack(side="left")

            ctk.CTkButton(
                row, text="✕", width=28, height=24, fg_color="#3d4659",
                command=lambda did=device.id: self._remove_device(did),
            ).pack(side="right", padx=(2, 6))
            ctk.CTkButton(
                row, text="✎", width=28, height=24, fg_color="#3d4659",
                command=lambda did=device.id, dname=device.name: self._rename_device(did, dname),
            ).pack(side="right", padx=2)

            if device.device_type == "smart_switch":
                ctk.CTkButton(
                    row, text="⌨", width=28, height=24, fg_color="#3d4659",
                    command=lambda did=device.id, dname=device.name: self._bind_device_hotkey_dialog(did, dname),
                ).pack(side="right", padx=2)
                switch_var = ctk.BooleanVar(value=is_on)
                switch = ctk.CTkSwitch(
                    row,
                    text="Вкл" if is_on else "Выкл",
                    variable=switch_var,
                    width=42,
                    progress_color="#2a9d5c",
                    button_color="#e8ecf4",
                    button_hover_color="#ffffff",
                    fg_color="#4a2230",
                )
                switch.configure(
                    command=lambda eid=device.entity_id, var=switch_var, sw=switch: self._on_device_switch_toggle(eid, var, sw),
                )
                switch.pack(side="right", padx=(8, 4), pady=4)
        self._refresh_switch_picker()
        self.request_resize()

    def _device_hotkey_hints(self, server_id: str) -> Dict[str, str]:
        """device_id → подпись клавиши (прямая или через группу)."""
        hints: Dict[str, str] = {}
        groups = {g.id: g for g in self._service.store.list_device_groups(server_id)}
        for entry in self._service.store.list_device_hotkeys():
            label = hotkey_label(entry.hotkey)
            if entry.device_id:
                hints[entry.device_id] = label
                continue
            if not entry.group_id:
                continue
            group = groups.get(entry.group_id)
            if not group:
                continue
            for device_id in group.device_ids:
                # прямая привязка приоритетнее групповой
                hints.setdefault(device_id, f"{label} · группа")
        return hints

    def _on_device_switch_toggle(
        self,
        entity_id: int,
        var: ctk.BooleanVar,
        switch_widget: Optional[ctk.CTkSwitch] = None,
    ) -> None:
        value = bool(var.get())
        self._service.toggle_device(entity_id, value)
        self._device_states.setdefault(entity_id, {})["value"] = value
        if switch_widget is not None and switch_widget.winfo_exists():
            switch_widget.configure(text="Вкл" if value else "Выкл")

    def _rename_device(self, device_id: str, current_name: str) -> None:
        dialog = ctk.CTkInputDialog(
            text=f"Новое имя (сейчас: {current_name}):",
            title="Переименовать",
        )
        name = dialog.get_input()
        if name is None:
            return
        name = name.strip()
        if not name:
            self._set_status("Имя не может быть пустым", error=True)
            return
        if self._service.store.rename_device(device_id, name) is None:
            self._set_status("Устройство не найдено", error=True)
            return
        self._set_status(f"Переименовано: {current_name} → {name}")
        self._refresh_devices_panel()
        self._refresh_groups_label()

    def _remove_device(self, device_id: str) -> None:
        self._service.store.remove_device(device_id)
        self._service.reload_device_hotkeys()
        self._refresh_devices_panel()
        self._refresh_groups_label()

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
        cam_id = camera_id.strip()
        if not cam_id:
            self._set_status("Введите ID камеры", error=True)
            self._overlay.show_live_alert("Камера: введите ID")
            return
        if not self._service.connection.is_connected:
            msg = "Сначала подключитесь к серверу"
            self._set_status(msg, error=True)
            self._overlay.show_live_alert(msg)
            print(f"[Rust+] camera open blocked: not connected ({cam_id})")
            return

        print(f"[Rust+] opening camera UI for {cam_id}")
        if self._camera_window and self._camera_window.is_open:
            # Не зовём close_camera здесь — open_camera сам закроет предыдущую подписку
            self._camera_window.close(notify_service=False)
            self._camera_window = None

        self._camera_window = CameraWindow(
            self._root,
            self._service,
            cam_id,
            status_text=f"Подключение к {cam_id}...",
        )
        self._set_status(f"Открытие камеры {cam_id}...")
        self._overlay.show_live_alert(f"Камера: подключение {cam_id}")
        self._service.open_camera(cam_id)

    def _close_camera_window(self, *, notify_service: bool = True) -> None:
        if self._camera_window and self._camera_window.is_open:
            self._camera_window.close(notify_service=notify_service)
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
            self._minimap.set_team(self._map_overlay_team(), self._map_size)
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
            team_members=self._map_overlay_team(),
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
            "spawn_patrol": alerts.spawn_patrol,
            "spawn_chinook": alerts.spawn_chinook,
            "spawn_cargo": alerts.spawn_cargo,
            "spawn_vendor": alerts.spawn_vendor,
            "cargo_arrival": alerts.cargo_arrival,
            "cargo_docking": alerts.cargo_docking,
            "cargo_departure": alerts.cargo_departure,
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
            self._minimap.update(path, self._map_overlay_team(), self._map_size)
            self._map_overlay_signature = None
            self._schedule_map_overlay_sync()
        except Exception:
            self._map_preview.configure(text="Не удалось показать карту")
        self.request_resize()

    def on_hide(self) -> None:
        if self._poll_job:
            self._root.after_cancel(self._poll_job)
            self._poll_job = None
        if self._event_dock_job:
            self._root.after_cancel(self._event_dock_job)
            self._event_dock_job = None

    def on_shutdown(self) -> None:
        self.on_hide()
        if self._root and self._vendors_render_job:
            try:
                self._root.after_cancel(self._vendors_render_job)
            except Exception:
                pass
            self._vendors_render_job = None
        if self._root and self._map_sync_job:
            try:
                self._root.after_cancel(self._map_sync_job)
            except Exception:
                pass
            self._map_sync_job = None
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
            try:
                self._apply_event(event)
            except Exception as exc:
                print(f"[Rust+] ошибка UI-обработчика {event.type}: {exc}")
                self._set_status(f"Ошибка UI ({event.type}): {exc}", error=True)

        self._root.after(0, apply)

    def _apply_event(self, event: RustPlusEvent) -> None:
        if event.type == EventType.STATUS:
            self._set_status(str(event.payload.get("message", "")))
            self._refresh_status()
        elif event.type == EventType.ERROR:
            msg = str(event.payload.get("message", "Ошибка"))
            self._set_status(msg, error=True)
            if "Камера" in msg:
                self._overlay.show_live_alert(msg)
                if self._camera_window and self._camera_window.is_open:
                    self._camera_window.set_status(msg, error=True)
                    print(f"[Rust+] camera error shown in window: {msg}")
        elif event.type == EventType.SERVER_PAIRED:
            self._refresh_servers()
        elif event.type == EventType.CONNECTED:
            self._refresh_servers()
            self._refresh_status()
            self._service.store.sync_devices_from_pairing_log(
                str(event.payload.get("server_id") or "") or None
            )
            self._refresh_devices_panel()
            self._service.refresh_device_states()
            if self._info_label:
                self._info_label.configure(text=f"Подключено: {event.payload.get('name', '')}")
            self._set_status(f"Подключено к {event.payload.get('name', '')}")
        elif event.type == EventType.DISCONNECTED:
            self._refresh_status()
            self._vendors_cache = []
            self._vendor_page = 0
            self._vendor_view_mode = "catalog"
            self._vendor_selected_item_id = None
            self._vendor_catalog_cache = []
            self._vendor_filtered_catalog = []
            self._vendor_offers_cache = []
            self._vendors_signature = None
            self._map_overlay_signature = None
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
            if self._vendor_back_btn:
                self._vendor_back_btn.pack_forget()
            if self._vendor_selected_label:
                self._vendor_selected_label.configure(text="")
            self._refresh_vendors_panel()
            self._refresh_devices_panel()
            if self._info_label:
                self._info_label.configure(text="Не подключено")
        elif event.type == EventType.SERVER_INFO:
            map_size = event.payload.get("map_size")
            if map_size:
                self._map_size = int(map_size)
                self._minimap.set_team(self._map_overlay_team(), self._map_size)
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
            self._schedule_map_overlay_sync()
        elif event.type == EventType.MARKERS:
            self._vendors_cache = event.payload.get("vendors", [])
            self._events_cache = event.payload.get("events", [])
            self._refresh_events_panel(self._events_cache)
            self._schedule_vendor_refresh()
            self._schedule_map_overlay_sync()
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
                self._schedule_map_overlay_sync()
        elif event.type == EventType.LIVE_ALERT:
            self._append_alert(
                str(event.payload.get("message", "Событие на сервере")),
                category=str(event.payload.get("category", "")),
            )
        elif event.type == EventType.DEVICE_PAIRED:
            self._refresh_devices_panel()
            self._refresh_groups_label()
            self._set_status(
                f"Устройство добавлено: {event.payload.get('name', 'Device')} "
                f"(#{event.payload.get('entity_id', '?')})"
            )
        elif event.type == EventType.CHAT_MESSAGE:
            self._append_chat(
                event.payload.get("name", "?"),
                event.payload.get("message", ""),
            )
        elif event.type == EventType.CAMERA_STATUS:
            cam_id = str(event.payload.get("camera_id", ""))
            if event.payload.get("open"):
                controls = {
                    "movement": bool(event.payload.get("movement")),
                    "mouse": bool(event.payload.get("mouse")),
                }
                if self._camera_window and self._camera_window.is_open:
                    self._camera_window.set_controls(controls)
                    self._camera_window.set_status(f"Камера {cam_id}: ожидание кадра...")
                else:
                    self._camera_window = CameraWindow(
                        self._root,
                        self._service,
                        cam_id,
                        controls=controls,
                        status_text=f"Камера {cam_id}: ожидание кадра...",
                    )
                self._set_status(f"Камера открыта: {cam_id}")
                self._overlay.show_live_alert(f"Камера открыта: {cam_id}")
                print(f"[Rust+] camera subscribed: {cam_id} controls={controls}")
            else:
                # Промежуточный close перед новым open — UI не трогаем,
                # иначе только что созданное окно мгновенно уничтожается.
                print(f"[Rust+] camera closed event (UI kept): {cam_id}")
        elif event.type == EventType.CAMERA_FRAME:
            frame_data = event.payload.get("data")
            path = event.payload.get("path")
            if self._camera_window and self._camera_window.is_open:
                if frame_data is not None:
                    self._camera_window.update_frame(frame_data)
                elif path:
                    self._camera_window.update_frame(str(path))
        self.request_resize()


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
