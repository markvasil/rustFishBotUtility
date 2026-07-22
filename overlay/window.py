from __future__ import annotations

import ctypes
from typing import Callable, Dict, List, Optional, Tuple

import customtkinter as ctk

from features.base import Feature
from overlay.smooth_scroll import SmoothScrollableFrame
from overlay.toast import ToastManager


class OverlayWindow:
    """Полупрозрачное окно поверх игры с переключением по F5.

    Размер окна фиксированный (тянется за уголок), а контент вкладок живёт
    внутри прокручиваемого фрейма. Окно НЕ подгоняется под контент — это
    убирает лаги при частой смене содержимого (например, во время сканирования).
    """

    BG_COLOR = "#0d1117"
    ACCENT = "#e07a3a"
    SIDEBAR_WIDTH = 190
    TOP_BAR_HEIGHT = 44
    MIN_WIDTH = 760
    MIN_HEIGHT = 360
    DEFAULT_WIDTH = 820
    DEFAULT_HEIGHT = 660
    GRIP_SIZE = 18

    def __init__(
        self,
        features: Optional[List[Feature]] = None,
        *,
        initial_position: Optional[Tuple[int, int]] = None,
        initial_size: Optional[Tuple[int, int]] = None,
        on_geometry_changed: Optional[Callable[[int, int, int, int], None]] = None,
    ) -> None:
        self._features: List[Feature] = []
        self._feature_map: Dict[str, Feature] = {}
        self._visible = False
        self._current_feature_id: Optional[str] = None
        self._nav_buttons: Dict[str, ctk.CTkButton] = {}
        self._feature_frames: Dict[str, ctk.CTkFrame] = {}
        self._nav_frame: Optional[ctk.CTkFrame] = None
        self._content: Optional[ctk.CTkFrame] = None
        self._saved_position = initial_position
        self._on_geometry_changed = on_geometry_changed

        self._width, self._height = self._clamp_size(
            *(initial_size or (self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT))
        )

        # Перетаскивание и ресайз коалесируются: гоняем geometry один раз за
        # цикл простоя, а не на каждое событие мыши (иначе слоёное окно лагает).
        self._drag_offset: Optional[Tuple[int, int]] = None
        self._pending_pos: Optional[Tuple[int, int]] = None
        self._move_job: Optional[str] = None
        self._resize_origin: Optional[Tuple[int, int, int, int]] = None
        self._pending_size: Optional[Tuple[int, int]] = None
        self._resize_job: Optional[str] = None

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.root = ctk.CTk()
        self._toast = ToastManager(self.root)
        self.root.title("Rust Utility Overlay")
        self.root.configure(fg_color=self.BG_COLOR)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.94)

        self._build_shell()
        self._apply_windows_styles()
        if features:
            self.set_features(features)
        self._apply_geometry()
        self.hide()

    # ---- фичи ----------------------------------------------------------------

    def set_features(self, features: List[Feature]) -> None:
        self._features = features
        self._feature_map = {f.id: f for f in features}
        self._mount_features()

    def get_feature(self, feature_id: str) -> Optional[Feature]:
        return self._feature_map.get(feature_id)

    def _build_shell(self) -> None:
        top_bar = ctk.CTkFrame(
            self.root, fg_color="#141a28", height=self.TOP_BAR_HEIGHT, corner_radius=0, cursor="fleur",
        )
        top_bar.pack(fill="x")
        top_bar.pack_propagate(False)

        accent = ctk.CTkFrame(top_bar, fg_color=self.ACCENT, height=3, corner_radius=0)
        accent.pack(fill="x", side="top")

        bar_body = ctk.CTkFrame(top_bar, fg_color="transparent", cursor="fleur")
        bar_body.pack(fill="both", expand=True)

        ctk.CTkLabel(
            bar_body,
            text="⠿",
            font=ctk.CTkFont(size=14),
            text_color="#6b7280",
            cursor="fleur",
        ).pack(side="left", padx=(10, 0), pady=8)

        ctk.CTkLabel(
            bar_body,
            text="Rust Utility",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#e8ecf4",
            cursor="fleur",
        ).pack(side="left", padx=(6, 14), pady=8)

        ctk.CTkLabel(
            bar_body,
            text="F5 — оверлей   ·   F6 — выход   ·   шапка — перемещение   ·   уголок — размер",
            font=ctk.CTkFont(size=11),
            text_color="#6b7280",
            cursor="fleur",
        ).pack(side="left", padx=4, pady=8)

        self._bind_drag_tree(top_bar)

        body = ctk.CTkFrame(self.root, fg_color="transparent")
        body.pack(fill="both", expand=True)

        sidebar = ctk.CTkFrame(body, fg_color="#141a28", width=self.SIDEBAR_WIDTH, corner_radius=0)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        self._nav_frame = ctk.CTkFrame(
            sidebar, fg_color="#141a28", width=self.SIDEBAR_WIDTH - 4, corner_radius=0,
        )
        self._nav_frame.pack(fill="both", expand=True)

        ctk.CTkLabel(
            self._nav_frame,
            text="Функции",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#8b93a7",
        ).pack(anchor="w", padx=14, pady=(14, 8))

        self._content = ctk.CTkFrame(body, fg_color=self.BG_COLOR, corner_radius=0)
        self._content.pack(side="left", fill="both", expand=True)

        self._build_resize_grip()

    def _build_resize_grip(self) -> None:
        grip = ctk.CTkLabel(
            self.root,
            text="◢",
            width=self.GRIP_SIZE,
            height=self.GRIP_SIZE,
            font=ctk.CTkFont(size=13),
            text_color="#6b7280",
            fg_color="transparent",
            cursor="sizing",
        )
        grip.place(relx=1.0, rely=1.0, anchor="se", x=-2, y=-2)
        grip.lift()
        grip.bind("<ButtonPress-1>", self._start_resize)
        grip.bind("<B1-Motion>", self._on_resize)
        grip.bind("<ButtonRelease-1>", self._end_resize)

    def _mount_features(self) -> None:
        assert self._nav_frame is not None and self._content is not None

        for widget in self._nav_frame.winfo_children():
            if isinstance(widget, ctk.CTkButton):
                widget.destroy()
        for frame in self._feature_frames.values():
            frame.destroy()

        self._nav_buttons.clear()
        self._feature_frames.clear()
        self._current_feature_id = None

        for feature in self._features:
            btn = ctk.CTkButton(
                self._nav_frame,
                text=feature.title,
                anchor="w",
                height=34,
                corner_radius=8,
                fg_color="transparent",
                hover_color="#242b3d",
                text_color="#d1d7e3",
                command=lambda fid=feature.id: self._show_feature(fid),
            )
            btn.pack(fill="x", padx=8, pady=2)
            self._nav_buttons[feature.id] = btn

            # Вкладку с собственным скроллом (Rust+) не оборачиваем — иначе два
            # слайдера. Остальные кладём в прокручиваемый фрейм: контент
            # переполняется в скролл, окно не растёт. request_resize — пустышка.
            if getattr(feature, "manages_own_scroll", False):
                frame = ctk.CTkFrame(self._content, fg_color=self.BG_COLOR, corner_radius=0)
            else:
                frame = SmoothScrollableFrame(self._content, fg_color=self.BG_COLOR, corner_radius=0)
            feature.set_request_resize(self._noop_resize)
            feature.build(frame)
            # place + lift: все вкладки уже в дереве и перекрывают друг друга,
            # без pack_forget/pack (он лагал на тяжёлых вкладках вроде Rust+).
            frame.place(relx=0, rely=0, relwidth=1, relheight=1)
            frame.lower()
            self._feature_frames[feature.id] = frame

        if self._features:
            self._show_feature(self._features[0].id)

    def _noop_resize(self) -> None:
        # Окно фиксированного размера — подгонять под контент не нужно.
        # Внутри вкладок работает скролл (SmoothScrollableFrame).
        pass

    def _show_feature(self, feature_id: str) -> None:
        if feature_id == self._current_feature_id:
            return

        prev_id = self._current_feature_id

        frame = self._feature_frames[feature_id]
        frame.lift()

        btn = self._nav_buttons[feature_id]
        btn.configure(fg_color="#2a3142", border_width=1, border_color="#e07a3a")

        if prev_id:
            prev_btn = self._nav_buttons.get(prev_id)
            if prev_btn:
                prev_btn.configure(fg_color="transparent", border_width=0)
            prev = self._feature_map.get(prev_id)
            if prev:
                prev.on_hide()

        self._current_feature_id = feature_id
        feature = self._feature_map[feature_id]
        # Тяжёлый on_show (особенно Rust+) — после отрисовки вкладки.
        self.root.after_idle(feature.on_show)

    # ---- геометрия / размер --------------------------------------------------

    def _clamp_size(self, width: int, height: int) -> Tuple[int, int]:
        screen_w = self.root.winfo_screenwidth() if hasattr(self, "root") else 100000
        screen_h = self.root.winfo_screenheight() if hasattr(self, "root") else 100000
        width = max(self.MIN_WIDTH, min(int(width), screen_w))
        height = max(self.MIN_HEIGHT, min(int(height), screen_h))
        return width, height

    def _apply_geometry(self) -> None:
        self.root.update_idletasks()
        self._width, self._height = self._clamp_size(self._width, self._height)
        w, h = self._width, self._height

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        if self._saved_position:
            x, y = self._saved_position
            x = max(0, min(x, screen_w - w))
            y = max(0, min(y, screen_h - h))
        else:
            x = (screen_w - w) // 2
            y = (screen_h - h) // 2
        self._saved_position = (x, y)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _persist_geometry(self) -> None:
        x, y = self.root.winfo_x(), self.root.winfo_y()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        self._saved_position = (x, y)
        self._width, self._height = w, h
        if self._on_geometry_changed:
            self._on_geometry_changed(x, y, w, h)

    # ---- перетаскивание ------------------------------------------------------

    def _bind_drag(self, widget) -> None:
        widget.bind("<ButtonPress-1>", self._start_drag, add="+")
        widget.bind("<B1-Motion>", self._on_drag, add="+")
        widget.bind("<ButtonRelease-1>", self._end_drag, add="+")

    def _bind_drag_tree(self, widget) -> None:
        self._bind_drag(widget)
        for child in widget.winfo_children():
            self._bind_drag_tree(child)

    def _start_drag(self, event) -> None:
        self._drag_offset = (
            event.x_root - self.root.winfo_x(),
            event.y_root - self.root.winfo_y(),
        )

    def _on_drag(self, event) -> None:
        if self._drag_offset is None:
            return
        self._pending_pos = (
            event.x_root - self._drag_offset[0],
            event.y_root - self._drag_offset[1],
        )
        if self._move_job is None:
            self._move_job = self.root.after_idle(self._apply_move)

    def _apply_move(self) -> None:
        self._move_job = None
        if self._pending_pos is None:
            return
        x, y = self._pending_pos
        self.root.geometry(f"+{x}+{y}")

    def _end_drag(self, _event) -> None:
        if self._drag_offset is None:
            return
        self._drag_offset = None
        if self._move_job is not None:
            self.root.after_cancel(self._move_job)
            self._move_job = None
        self._apply_move()
        self._persist_geometry()

    # ---- ресайз за уголок ----------------------------------------------------

    def _start_resize(self, event) -> None:
        self._resize_origin = (
            event.x_root,
            event.y_root,
            self.root.winfo_width(),
            self.root.winfo_height(),
        )

    def _on_resize(self, event) -> None:
        if self._resize_origin is None:
            return
        start_x, start_y, start_w, start_h = self._resize_origin
        w = start_w + (event.x_root - start_x)
        h = start_h + (event.y_root - start_y)
        self._pending_size = self._clamp_size(w, h)
        if self._resize_job is None:
            self._resize_job = self.root.after_idle(self._apply_resize)

    def _apply_resize(self) -> None:
        self._resize_job = None
        if self._pending_size is None:
            return
        w, h = self._pending_size
        self._width, self._height = w, h
        self.root.geometry(f"{w}x{h}")

    def _end_resize(self, _event) -> None:
        if self._resize_origin is None:
            return
        self._resize_origin = None
        if self._resize_job is not None:
            self.root.after_cancel(self._resize_job)
            self._resize_job = None
        self._apply_resize()
        self._persist_geometry()

    # ---- окно ----------------------------------------------------------------

    def _apply_windows_styles(self) -> None:
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            style |= 0x00080000
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, style)
        except Exception:
            pass

    def toggle(self) -> None:
        if self._visible:
            self.hide()
        else:
            self.show()

    def show(self) -> None:
        self._visible = True
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after_idle(self.root.focus_force)

    def hide(self) -> None:
        self._visible = False
        self.root.withdraw()

    def is_visible(self) -> bool:
        return self._visible

    def show_live_alert(self, message: str) -> None:
        self._toast.show(message)

    def run(self) -> None:
        self.root.mainloop()

    def quit(self) -> None:
        try:
            self.root.quit()
        except Exception:
            pass

    def destroy(self) -> None:
        try:
            self.root.destroy()
        except Exception:
            pass
