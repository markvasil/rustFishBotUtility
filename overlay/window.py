from __future__ import annotations

import ctypes
from typing import Dict, List, Optional

import customtkinter as ctk

from features.base import Feature
from overlay.toast import ToastManager


class OverlayWindow:
    """Полупрозрачное окно поверх игры с переключением по F5."""

    BG_COLOR = "#0d1117"
    ACCENT = "#e07a3a"
    SIDEBAR_WIDTH = 190
    TOP_BAR_HEIGHT = 44
    MIN_WIDTH = 640
    MIN_HEIGHT = 320

    def __init__(self, features: Optional[List[Feature]] = None) -> None:
        self._features: List[Feature] = []
        self._feature_map: Dict[str, Feature] = {}
        self._visible = False
        self._current_feature_id: Optional[str] = None
        self._resize_job: Optional[str] = None
        self._nav_buttons: Dict[str, ctk.CTkButton] = {}
        self._feature_frames: Dict[str, ctk.CTkFrame] = {}
        self._nav_frame: Optional[ctk.CTkScrollableFrame] = None
        self._content: Optional[ctk.CTkFrame] = None

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.root = ctk.CTk()
        self._toast = ToastManager(self.root)
        self.root.title("Rust Utility Overlay")
        self.root.configure(fg_color=self.BG_COLOR)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.94)
        self.root.resizable(False, False)

        self._build_shell()
        self._apply_windows_styles()
        if features:
            self.set_features(features)
        self.fit_to_content()
        self.hide()

    def set_features(self, features: List[Feature]) -> None:
        self._features = features
        self._feature_map = {f.id: f for f in features}
        self._mount_features()

    def get_feature(self, feature_id: str) -> Optional[Feature]:
        return self._feature_map.get(feature_id)

    def _build_shell(self) -> None:
        top_bar = ctk.CTkFrame(self.root, fg_color="#141a28", height=self.TOP_BAR_HEIGHT, corner_radius=0)
        top_bar.pack(fill="x")
        top_bar.pack_propagate(False)

        accent = ctk.CTkFrame(top_bar, fg_color=self.ACCENT, height=3, corner_radius=0)
        accent.pack(fill="x", side="top")

        bar_body = ctk.CTkFrame(top_bar, fg_color="transparent")
        bar_body.pack(fill="both", expand=True)

        ctk.CTkLabel(
            bar_body,
            text="Rust Utility",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#e8ecf4",
        ).pack(side="left", padx=14, pady=8)

        ctk.CTkLabel(
            bar_body,
            text="F5 — оверлей   ·   F6 — выход",
            font=ctk.CTkFont(size=11),
            text_color="#6b7280",
        ).pack(side="left", padx=4, pady=8)

        body = ctk.CTkFrame(self.root, fg_color="transparent")
        body.pack(fill="x")

        sidebar = ctk.CTkFrame(body, fg_color="#141a28", width=self.SIDEBAR_WIDTH, corner_radius=0)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        self._nav_frame = ctk.CTkScrollableFrame(
            sidebar, fg_color="#141a28", width=self.SIDEBAR_WIDTH - 4,
            height=420, corner_radius=0,
        )
        self._nav_frame.pack(fill="both", expand=True)

        ctk.CTkLabel(
            self._nav_frame,
            text="Функции",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#8b93a7",
        ).pack(anchor="w", padx=14, pady=(14, 8))

        self._content = ctk.CTkFrame(body, fg_color=self.BG_COLOR, corner_radius=0)
        self._content.pack(side="left", fill="y")

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

            frame = ctk.CTkFrame(self._content, fg_color=self.BG_COLOR)
            feature.set_request_resize(self.fit_to_content)
            feature.build(frame)
            self._feature_frames[feature.id] = frame

        if self._features:
            self._show_feature(self._features[0].id)

    def fit_to_content(self) -> None:
        if self._resize_job:
            self.root.after_cancel(self._resize_job)
        self._resize_job = self.root.after(0, self._apply_fit)

    def _apply_fit(self) -> None:
        self._resize_job = None
        self.root.update_idletasks()

        content_width = self.MIN_WIDTH - self.SIDEBAR_WIDTH
        content_height = self.MIN_HEIGHT - self.TOP_BAR_HEIGHT

        if self._current_feature_id:
            frame = self._feature_frames[self._current_feature_id]
            frame.update_idletasks()
            content_width = max(content_width, frame.winfo_reqwidth())
            content_height = max(content_height, frame.winfo_reqheight())

        width = self.SIDEBAR_WIDTH + content_width
        height = self.TOP_BAR_HEIGHT + content_height

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        width = min(width, screen_w - 40)
        height = min(height, screen_h - 40)

        x = (screen_w - width) // 2
        y = (screen_h - height) // 2

        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _show_feature(self, feature_id: str) -> None:
        if feature_id == self._current_feature_id:
            return

        if self._current_feature_id:
            prev = self._feature_map.get(self._current_feature_id)
            if prev:
                prev.on_hide()
            prev_frame = self._feature_frames.get(self._current_feature_id)
            if prev_frame:
                prev_frame.pack_forget()
            prev_btn = self._nav_buttons.get(self._current_feature_id)
            if prev_btn:
                prev_btn.configure(fg_color="transparent", border_width=0)

        self._current_feature_id = feature_id
        frame = self._feature_frames[feature_id]
        frame.pack(fill="x")

        btn = self._nav_buttons[feature_id]
        btn.configure(fg_color="#2a3142", border_width=1, border_color="#e07a3a")

        feature = self._feature_map[feature_id]
        feature.on_show()
        self.fit_to_content()

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
        self.fit_to_content()
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.focus_force()

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
