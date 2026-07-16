from __future__ import annotations

import tkinter as tk
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import customtkinter as ctk
from PIL import Image, ImageTk

from services.rustplus.live_format import has_active_motion, project_motion
from services.rustplus.map_renderer import MapRenderer


class MapWindow:
    """Интерактивная карта: zoom/pan, follow, event tracking, рисование."""

    TICK_MS = 100

    def __init__(
        self,
        root: ctk.CTk,
        image_path: str | Path,
        *,
        map_size: Optional[int] = None,
        team_members: Optional[List[Dict[str, Any]]] = None,
        death_markers: Optional[List[Dict[str, Any]]] = None,
        drawings: Optional[List[Dict[str, Any]]] = None,
        events: Optional[List[Dict[str, Any]]] = None,
        vendors: Optional[List[Dict[str, Any]]] = None,
        tracked_event_id: Optional[int] = None,
        follow_steam_id: Optional[int] = None,
        on_close: Optional[Callable[[], None]] = None,
        on_track_event: Optional[Callable[[Optional[int]], None]] = None,
        on_add_drawing: Optional[Callable[[float, float, str], None]] = None,
        renderer: Optional[MapRenderer] = None,
    ) -> None:
        self._root = root
        self._path = str(image_path)
        self._map_size = map_size
        self._team = team_members or []
        self._deaths = death_markers or []
        self._drawings = drawings or []
        self._events = events or []
        self._vendors = vendors or []
        self._tracked_event_id = tracked_event_id
        self._follow_steam_id = follow_steam_id
        self._on_close = on_close
        self._on_track_event = on_track_event
        self._on_add_drawing = on_add_drawing
        self._renderer = renderer or MapRenderer()
        self._zoom = 1.0
        # Центр вьюпорта в координатах базовой карты (пиксели JPEG).
        self._view_cx: Optional[float] = None
        self._view_cy: Optional[float] = None
        self._drag_last: Optional[tuple[int, int]] = None
        self._press_pos: Optional[tuple[int, int]] = None
        self._photo: Optional[ImageTk.PhotoImage] = None
        self._tick_job: Optional[str] = None
        self._dirty = True
        self._rendering = False
        self._base_size: Optional[tuple[int, int]] = None
        self._last_canvas_size: tuple[int, int] = (0, 0)

        self._win = ctk.CTkToplevel(root)
        self._win.title("Rust+ — карта сервера")
        self._win.configure(fg_color="#0d1117")
        self._win.attributes("-topmost", True)

        bar = ctk.CTkFrame(self._win, fg_color="#141a28", height=40, corner_radius=0)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        ctk.CTkLabel(
            bar,
            text="Num +/- зум | ЛКМ pan | клик события — трек | ПКМ — метка | Esc — закрыть",
            font=ctk.CTkFont(size=11),
            text_color="#8b93a7",
        ).pack(side="left", padx=12)
        ctk.CTkButton(bar, text="✕", width=32, height=28, fg_color="#4a2230", command=self.close).pack(
            side="right", padx=8, pady=4,
        )

        self._canvas = tk.Canvas(self._win, bg="#0d1117", highlightthickness=0)
        self._canvas.pack(fill="both", expand=True, padx=8, pady=8)

        win_w = min(int(root.winfo_screenwidth() * 0.92), 1200)
        win_h = min(int(root.winfo_screenheight() * 0.9), 900)
        x = (root.winfo_screenwidth() - win_w) // 2
        y = (root.winfo_screenheight() - win_h) // 2
        self._win.geometry(f"{win_w}x{win_h}+{x}+{y}")
        self._win.protocol("WM_DELETE_WINDOW", self.close)
        self._win.bind("<Escape>", lambda _e: self.close())
        self._canvas.bind("<ButtonPress-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self._canvas.bind("<Button-3>", self._on_right_click)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._win.bind("<KeyPress>", self._on_key)
        self._win.focus_force()
        self._mark_dirty()
        # Не рендерим сразу: у canvas ещё нет реального размера (1×1).
        self._win.after_idle(self._render_when_ready)
        self._start_tick()

    @property
    def is_open(self) -> bool:
        try:
            return self._win.winfo_exists()
        except Exception:
            return False

    def _mark_dirty(self) -> None:
        self._dirty = True

    def _base_dimensions(self) -> tuple[int, int]:
        if self._base_size is None:
            self._base_size = self._renderer.get_base_size(self._path)
        return self._base_size

    def _ensure_view_center(self) -> tuple[float, float]:
        """Центр вьюпорта на базовой карте; по умолчанию — середина."""
        base_w, base_h = self._base_dimensions()
        if self._view_cx is None or self._view_cy is None:
            self._view_cx = base_w / 2.0
            self._view_cy = base_h / 2.0
        return float(self._view_cx), float(self._view_cy)

    def _clamp_view_center(self) -> None:
        """Не даём кропу уехать за край карты."""
        if self._view_cx is None or self._view_cy is None:
            return
        base_w, base_h = self._base_dimensions()
        zoom = max(self._zoom, 1.0)
        crop_w = base_w / zoom
        crop_h = base_h / zoom
        half_w = crop_w / 2.0
        half_h = crop_h / 2.0
        self._view_cx = max(half_w, min(float(self._view_cx), base_w - half_w))
        self._view_cy = max(half_h, min(float(self._view_cy), base_h - half_h))

    def update_state(
        self,
        *,
        team_members: Optional[List[Dict[str, Any]]] = None,
        members: Optional[List[Dict[str, Any]]] = None,
        death_markers: Optional[List[Dict[str, Any]]] = None,
        drawings: Optional[List[Dict[str, Any]]] = None,
        events: Optional[List[Dict[str, Any]]] = None,
        vendors: Optional[List[Dict[str, Any]]] = None,
        tracked_event_id: Optional[int] = None,
        follow_steam_id: Optional[int] = None,
        map_size: Optional[int] = None,
    ) -> None:
        if members is not None:
            team_members = members
        if team_members is not None:
            self._team = team_members
        if death_markers is not None:
            self._deaths = death_markers
        if drawings is not None:
            self._drawings = drawings
        if events is not None:
            self._events = events
        if vendors is not None:
            self._vendors = vendors
        if tracked_event_id is not None:
            self._tracked_event_id = tracked_event_id
        if follow_steam_id is not None:
            self._follow_steam_id = follow_steam_id
        if map_size:
            self._map_size = map_size
        self._mark_dirty()

    def close(self) -> None:
        if self._tick_job:
            try:
                self._win.after_cancel(self._tick_job)
            except Exception:
                pass
            self._tick_job = None
        if self.is_open:
            self._win.destroy()
        if self._on_close:
            self._on_close()

    def lift(self) -> None:
        if self.is_open:
            self._win.lift()

    def _has_moving_overlay(self) -> bool:
        for group in (self._team, self._events, self._vendors):
            for item in group:
                if has_active_motion(item):
                    return True
        return False

    def _start_tick(self) -> None:
        def tick():
            if self.is_open:
                if self._follow_steam_id or self._dirty or self._has_moving_overlay():
                    self._render_frame()
                self._tick_job = self._win.after(self.TICK_MS, tick)
        self._tick_job = self._win.after(self.TICK_MS, tick)

    def _on_canvas_configure(self, event) -> None:
        if event.width < 50 or event.height < 50:
            return
        size = (int(event.width), int(event.height))
        if size == self._last_canvas_size:
            return
        self._last_canvas_size = size
        self._mark_dirty()
        self._render_frame()

    def _render_when_ready(self) -> None:
        if not self.is_open:
            return
        try:
            self._win.update_idletasks()
        except Exception:
            pass
        cw = int(self._canvas.winfo_width())
        ch = int(self._canvas.winfo_height())
        if cw < 50 or ch < 50:
            self._win.after(50, self._render_when_ready)
            return
        self._last_canvas_size = (cw, ch)
        self._render_frame()

    def _render_frame(self) -> None:
        if not self.is_open or self._rendering:
            return
        cw = int(self._canvas.winfo_width())
        ch = int(self._canvas.winfo_height())
        if cw < 50 or ch < 50:
            return
        self._rendering = True
        try:
            projected_team = project_motion(self._team, map_size=self._map_size)
            projected_events = project_motion(self._events, map_size=self._map_size)
            projected_vendors = project_motion(self._vendors, map_size=self._map_size)
            center = self._ensure_view_center()
            if self._follow_steam_id and self._map_size:
                base_w, base_h = self._base_dimensions()
                for member in projected_team:
                    if int(member.get("steam_id", 0)) == int(self._follow_steam_id):
                        from services.rustplus.live_format import world_to_map_pixel

                        px, py = world_to_map_pixel(
                            float(member["x"]), float(member["y"]), self._map_size, base_w, base_h,
                        )
                        center = (float(px), float(py))
                        self._view_cx, self._view_cy = center
                        break

            # При zoom=1.0 показываем карту целиком без кропа.
            use_center = center if self._zoom > 1.0 else None
            image = self._renderer.render(
                self._path,
                map_size=self._map_size,
                team_members=projected_team,
                death_markers=self._deaths,
                drawings=self._drawings,
                events=projected_events,
                vendors=projected_vendors,
                tracked_event_id=self._tracked_event_id,
                follow_steam_id=None,
                view_center=use_center,
                zoom=self._zoom,
                output_size=(cw, ch),
            )
            self._photo = ImageTk.PhotoImage(image)
            self._canvas.delete("all")
            self._canvas.create_image(0, 0, anchor="nw", image=self._photo)
            self._dirty = False
        finally:
            self._rendering = False

    def _on_key(self, event) -> None:
        if event.keysym in ("KP_Add", "plus", "equal"):
            self._ensure_view_center()
            self._zoom = min(4.0, self._zoom + 0.15)
            self._clamp_view_center()
            self._mark_dirty()
            self._render_frame()
        elif event.keysym in ("KP_Subtract", "minus"):
            self._zoom = max(1.0, self._zoom - 0.15)
            if self._zoom <= 1.0:
                self._zoom = 1.0
            else:
                self._clamp_view_center()
            self._mark_dirty()
            self._render_frame()

    def _on_press(self, event) -> None:
        self._press_pos = (event.x, event.y)
        self._drag_last = (event.x, event.y)

    def _on_drag(self, event) -> None:
        if not self._drag_last:
            return
        if self._zoom <= 1.0:
            # На полном виде pan не нужен — карта и так целиком.
            self._drag_last = (event.x, event.y)
            return
        dx = event.x - self._drag_last[0]
        dy = event.y - self._drag_last[1]
        self._drag_last = (event.x, event.y)
        if dx == 0 and dy == 0:
            return

        # Дельту canvas → координаты базовой карты (размер кропа / размер окна).
        base_w, base_h = self._base_dimensions()
        cw = max(int(self._canvas.winfo_width()), 1)
        ch = max(int(self._canvas.winfo_height()), 1)
        crop_w = base_w / self._zoom
        crop_h = base_h / self._zoom
        # Тянем карту за курсором: вправо → смотрим левее.
        cx, cy = self._ensure_view_center()
        self._view_cx = cx - dx * (crop_w / cw)
        self._view_cy = cy - dy * (crop_h / ch)
        self._clamp_view_center()
        self._mark_dirty()
        # Не блокируем следующий кадр: если рендер занят, тик дорисует по dirty.
        if not self._rendering:
            self._render_frame()

    def _on_release(self, event) -> None:
        press = self._press_pos
        self._press_pos = None
        self._drag_last = None
        if not press or not self._map_size:
            return
        moved = abs(event.x - press[0]) + abs(event.y - press[1])
        if moved > 6:
            return
        self._try_track_event(event.x, event.y)

    def _canvas_to_base(self, canvas_x: int, canvas_y: int) -> tuple[float, float]:
        """Пиксели окна → пиксели базовой карты с учётом zoom/pan."""
        base_w, base_h = self._base_dimensions()
        cw = max(int(self._canvas.winfo_width()), 1)
        ch = max(int(self._canvas.winfo_height()), 1)
        if self._zoom <= 1.0:
            return canvas_x / cw * base_w, canvas_y / ch * base_h
        cx, cy = self._ensure_view_center()
        crop_w = base_w / self._zoom
        crop_h = base_h / self._zoom
        left = cx - crop_w / 2.0
        top = cy - crop_h / 2.0
        return left + canvas_x / cw * crop_w, top + canvas_y / ch * crop_h

    def _try_track_event(self, cx: int, cy: int) -> None:
        from services.rustplus.live_format import world_to_map_pixel

        base_w, base_h = self._base_dimensions()
        click_x, click_y = self._canvas_to_base(cx, cy)
        best = None
        best_dist = 9999.0
        # Порог в координатах базовой карты (зависит от зума).
        threshold = max(18.0, 28.0 / max(self._zoom, 1.0))
        for event in self._events:
            x, y = event.get("x"), event.get("y")
            if x is None:
                continue
            px, py = world_to_map_pixel(float(x), float(y), self._map_size, base_w, base_h)
            dist = abs(px - click_x) + abs(py - click_y)
            if dist < threshold and dist < best_dist:
                best = event
                best_dist = dist
        if best and self._on_track_event:
            self._on_track_event(int(best.get("id")))
            self._tracked_event_id = int(best.get("id"))
            self._mark_dirty()
            self._render_frame()

    def _on_right_click(self, event) -> None:
        if not self._on_add_drawing or not self._map_size:
            return

        base_w, base_h = self._base_dimensions()
        px, py = self._canvas_to_base(event.x, event.y)
        wx = px / base_w * self._map_size
        wy = self._map_size - py / base_h * self._map_size
        dialog = ctk.CTkInputDialog(text="Текст метки:", title="Метка на карте")
        text = dialog.get_input()
        if text:
            self._on_add_drawing(wx, wy, text)
