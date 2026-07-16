from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import customtkinter as ctk
from PIL import Image

from services.rustplus.map_renderer import MapRenderer
from services.rustplus.live_format import has_active_motion, project_motion


class MinimapWindow:
    """Компактная карта поверх игры (always-on-top) с drag и оверлеями."""

    PREVIEW_SIZE = (300, 300)
    MOVE_REFRESH_MS = 120

    def __init__(
        self,
        root: ctk.CTk,
        initial_position: Optional[tuple[int, int]] = None,
        on_position_changed: Optional[Callable[[int, int], None]] = None,
        renderer: Optional[MapRenderer] = None,
    ) -> None:
        self._root = root
        self._win: Optional[ctk.CTkToplevel] = None
        self._label: Optional[ctk.CTkLabel] = None
        self._image_ref: Optional[ctk.CTkImage] = None
        self._visible = False
        self._path: Optional[str] = None
        self._team_members: List[Dict[str, Any]] = []
        self._death_markers: List[Dict[str, Any]] = []
        self._drawings: List[Dict[str, Any]] = []
        self._events: List[Dict[str, Any]] = []
        self._vendors: List[Dict[str, Any]] = []
        self._map_size: Optional[int] = None
        self._follow_steam_id: Optional[int] = None
        self._tracked_event_id: Optional[int] = None
        self._saved_position = initial_position
        self._on_position_changed = on_position_changed
        self._drag_offset: Optional[tuple[int, int]] = None
        self._renderer = renderer or MapRenderer()
        self._render_job: Optional[str] = None
        self._motion_tick_job: Optional[str] = None
        self._render_delay_ms = 1200
        self._render_token = 0
        self._rendering = False
        self._pil_ref = None

    @property
    def is_visible(self) -> bool:
        return self._visible and self._win is not None and self._win.winfo_exists()

    def set_overlay_state(
        self,
        *,
        members: Optional[List[Dict[str, Any]]] = None,
        map_size: Optional[int] = None,
        death_markers: Optional[List[Dict[str, Any]]] = None,
        drawings: Optional[List[Dict[str, Any]]] = None,
        events: Optional[List[Dict[str, Any]]] = None,
        vendors: Optional[List[Dict[str, Any]]] = None,
        follow_steam_id: Optional[int] = None,
        tracked_event_id: Optional[int] = None,
    ) -> None:
        if members is not None:
            self._team_members = members
        if map_size:
            self._map_size = map_size
        if death_markers is not None:
            self._death_markers = death_markers
        if drawings is not None:
            self._drawings = drawings
        if events is not None:
            self._events = events
        if vendors is not None:
            self._vendors = vendors
        if follow_steam_id is not None:
            self._follow_steam_id = follow_steam_id
        if tracked_event_id is not None:
            self._tracked_event_id = tracked_event_id
        if self.is_visible and self._path:
            if self._has_moving_overlay():
                self._ensure_motion_tick()
                self._schedule_apply_image(self.MOVE_REFRESH_MS)
            else:
                self._stop_motion_tick()
                self._schedule_apply_image(self._render_delay_ms)

    def _has_moving_overlay(self) -> bool:
        for group in (self._team_members, self._events, self._vendors):
            for item in group:
                if has_active_motion(item):
                    return True
        return False

    def _ensure_motion_tick(self) -> None:
        if self._motion_tick_job:
            return

        def tick() -> None:
            self._motion_tick_job = None
            if not self.is_visible or not self._path:
                return
            if not self._has_moving_overlay():
                return
            self._schedule_apply_image(0)
            self._motion_tick_job = self._root.after(self.MOVE_REFRESH_MS, tick)

        self._motion_tick_job = self._root.after(self.MOVE_REFRESH_MS, tick)

    def _stop_motion_tick(self) -> None:
        if self._motion_tick_job:
            try:
                self._root.after_cancel(self._motion_tick_job)
            except Exception:
                pass
            self._motion_tick_job = None

    def _schedule_apply_image(self, delay_ms: Optional[int] = None) -> None:
        if self._render_job:
            self._root.after_cancel(self._render_job)
        delay = self._render_delay_ms if delay_ms is None else int(delay_ms)
        self._render_job = self._root.after(delay, self._run_apply_image)

    def _run_apply_image(self) -> None:
        self._render_job = None
        if self.is_visible and self._path:
            self._apply_image(self._path)

    def set_team(self, members: List[Dict[str, Any]], map_size: Optional[int]) -> None:
        self.set_overlay_state(members=members, map_size=map_size)

    def toggle(self, image_path: Optional[str] = None) -> bool:
        if image_path:
            self._path = image_path
        if self.is_visible:
            self.hide()
            return False
        if not self._path:
            return False
        self.show(self._path)
        return True

    def show(self, image_path: str | Path) -> None:
        self._path = str(image_path)
        if self._win is None or not self._win.winfo_exists():
            self._win = ctk.CTkToplevel(self._root)
            self._win.title("Rust+ Minimap")
            self._win.overrideredirect(True)
            self._win.attributes("-topmost", True)
            self._win.attributes("-alpha", 0.88)
            self._win.configure(fg_color="#0d1117")
        if self._label is None:
            self._label = ctk.CTkLabel(self._win, text="Подготовка миникарты…", cursor="fleur")
            self._label.pack(padx=4, pady=4)
            self._bind_drag(self._win)
            self._bind_drag(self._label)
            self._win.bind("<Button-3>", lambda _e: self.hide())
        elif self._label:
            self._label.configure(text="Подготовка миникарты…", image=None)

        self._apply_image(self._path, show_busy=True)
        self._place_window()
        self._win.deiconify()
        self._win.lift()
        self._visible = True
        if self._has_moving_overlay():
            self._ensure_motion_tick()

    def update(
        self,
        image_path: str | Path,
        members: Optional[List[Dict[str, Any]]] = None,
        map_size: Optional[int] = None,
    ) -> None:
        self._path = str(image_path)
        self.set_overlay_state(members=members, map_size=map_size)
        if self.is_visible:
            self._apply_image(self._path)

    def hide(self) -> None:
        self._visible = False
        self._drag_offset = None
        self._stop_motion_tick()
        if self._render_job:
            self._root.after_cancel(self._render_job)
            self._render_job = None
        if self._win and self._win.winfo_exists():
            self._win.withdraw()

    def destroy(self) -> None:
        self._visible = False
        self._drag_offset = None
        self._stop_motion_tick()
        if self._render_job:
            self._root.after_cancel(self._render_job)
            self._render_job = None
        if self._win and self._win.winfo_exists():
            self._win.destroy()
        self._win = None

    def _place_window(self) -> None:
        if not self._win:
            return
        win_w = self.PREVIEW_SIZE[0] + 8
        win_h = self.PREVIEW_SIZE[1] + 8
        if self._saved_position:
            x, y = self._saved_position
        else:
            screen_w = self._root.winfo_screenwidth()
            x = screen_w - self.PREVIEW_SIZE[0] - 24
            y = 60
        self._win.geometry(f"{win_w}x{win_h}+{x}+{y}")

    def _bind_drag(self, widget) -> None:
        widget.bind("<ButtonPress-1>", self._start_drag, add="+")
        widget.bind("<B1-Motion>", self._on_drag, add="+")
        widget.bind("<ButtonRelease-1>", self._end_drag, add="+")

    def _start_drag(self, event) -> None:
        if not self._win:
            return
        self._drag_offset = (
            event.x_root - self._win.winfo_x(),
            event.y_root - self._win.winfo_y(),
        )

    def _on_drag(self, event) -> None:
        if not self._win or self._drag_offset is None:
            return
        x = event.x_root - self._drag_offset[0]
        y = event.y_root - self._drag_offset[1]
        self._win.geometry(f"+{x}+{y}")

    def _end_drag(self, _event) -> None:
        if not self._win:
            return
        self._drag_offset = None
        x, y = self._win.winfo_x(), self._win.winfo_y()
        self._saved_position = (x, y)
        if self._on_position_changed:
            self._on_position_changed(x, y)

    def _apply_image(self, path: str, *, show_busy: bool = False) -> None:
        if not self._label or self._rendering:
            return
        self._rendering = True
        self._render_token += 1
        token = self._render_token
        if show_busy and self._label:
            self._label.configure(text="Обновление миникарты…", image=None)

        def worker() -> None:
            try:
                image = self._render_image(path)
                image.thumbnail(self.PREVIEW_SIZE, Image.Resampling.LANCZOS)
            except Exception as exc:
                self._root.after(0, lambda: self._finish_render_error(str(exc), token))
                return
            self._root.after(0, lambda: self._finish_render_ok(image, token))

        threading.Thread(target=worker, daemon=True, name="MinimapRender").start()

    def _finish_render_ok(self, image: Image.Image, token: int) -> None:
        self._rendering = False
        self._show_rendered_image(image, token)

    def _finish_render_error(self, message: str, token: int) -> None:
        self._rendering = False
        self._show_render_error(message, token)

    def _show_rendered_image(self, image: Image.Image, token: int) -> None:
        if token != self._render_token or not self._label:
            return
        try:
            image = image.convert("RGB").copy()
            self._pil_ref = image
            new_ref = ctk.CTkImage(
                light_image=image,
                dark_image=image.copy(),
                size=(image.width, image.height),
            )
            self._label.configure(image=new_ref, text="")
            self._image_ref = new_ref
        except Exception as exc:
            try:
                self._label.configure(image="", text=str(exc), text_color="#f87171")
            except Exception:
                pass

    def _show_render_error(self, message: str, token: int) -> None:
        if token != self._render_token or not self._label:
            return
        self._label.configure(image=None, text=message, text_color="#f87171")

    def _render_image(self, path: str) -> Image.Image:
        return self._renderer.render(
            path,
            map_size=self._map_size,
            team_members=project_motion(self._team_members, map_size=self._map_size),
            death_markers=self._death_markers,
            drawings=self._drawings,
            events=project_motion(self._events, map_size=self._map_size),
            vendors=project_motion(self._vendors, map_size=self._map_size),
            tracked_event_id=self._tracked_event_id,
            follow_steam_id=self._follow_steam_id,
            zoom=1.4 if self._follow_steam_id else 1.0,
            output_size=self.PREVIEW_SIZE,
        )
