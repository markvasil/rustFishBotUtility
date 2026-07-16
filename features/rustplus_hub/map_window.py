from __future__ import annotations

import tkinter as tk
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import customtkinter as ctk
from PIL import Image, ImageTk

from services.rustplus.live_format import project_motion
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
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._drag_start: Optional[tuple[int, int]] = None
        self._photo: Optional[ImageTk.PhotoImage] = None
        self._tick_job: Optional[str] = None
        self._dirty = True
        self._rendering = False
        self._base_size: Optional[tuple[int, int]] = None

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
        self._win.bind("<KeyPress>", self._on_key)
        self._win.focus_force()
        self._mark_dirty()
        self._render_frame()
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

    def _start_tick(self) -> None:
        def tick():
            if self.is_open:
                if self._follow_steam_id or self._dirty:
                    self._render_frame()
                self._tick_job = self._win.after(self.TICK_MS, tick)
        self._tick_job = self._win.after(self.TICK_MS, tick)

    def _render_frame(self) -> None:
        if not self.is_open or self._rendering:
            return
        self._rendering = True
        try:
            cw = max(self._canvas.winfo_width(), 400)
            ch = max(self._canvas.winfo_height(), 300)
            projected_team = project_motion(self._team, map_size=self._map_size)
            projected_events = project_motion(self._events, map_size=self._map_size)
            projected_vendors = project_motion(self._vendors, map_size=self._map_size)
            center = (self._pan_x, self._pan_y)
            if self._follow_steam_id and self._map_size:
                base_w, base_h = self._base_dimensions()
                for member in projected_team:
                    if int(member.get("steam_id", 0)) == int(self._follow_steam_id):
                        from services.rustplus.live_format import world_to_map_pixel

                        px, py = world_to_map_pixel(
                            float(member["x"]), float(member["y"]), self._map_size, base_w, base_h,
                        )
                        center = (float(px), float(py))
                        break

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
                view_center=center,
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
            self._zoom = min(4.0, self._zoom + 0.15)
            self._mark_dirty()
            self._render_frame()
        elif event.keysym in ("KP_Subtract", "minus"):
            self._zoom = max(1.0, self._zoom - 0.15)
            self._mark_dirty()
            self._render_frame()

    def _on_press(self, event) -> None:
        self._drag_start = (event.x, event.y)

    def _on_drag(self, event) -> None:
        if not self._drag_start:
            return
        dx = event.x - self._drag_start[0]
        dy = event.y - self._drag_start[1]
        self._drag_start = (event.x, event.y)
        self._pan_x += dx
        self._pan_y += dy
        self._mark_dirty()
        self._render_frame()

    def _on_release(self, event) -> None:
        if not self._drag_start or not self._map_size:
            self._drag_start = None
            return
        moved = abs(event.x - self._drag_start[0]) + abs(event.y - self._drag_start[1])
        self._drag_start = None
        if moved > 6:
            return
        self._try_track_event(event.x, event.y)

    def _try_track_event(self, cx: int, cy: int) -> None:
        from services.rustplus.live_format import world_to_map_pixel

        base_w, base_h = self._base_dimensions()
        best = None
        best_dist = 9999
        for event in self._events:
            x, y = event.get("x"), event.get("y")
            if x is None:
                continue
            px, py = world_to_map_pixel(float(x), float(y), self._map_size, base_w, base_h)
            dist = abs(px - cx) + abs(py - cy)
            if dist < 24 and dist < best_dist:
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
        inv_zoom = self._zoom
        px = int((event.x / max(self._canvas.winfo_width(), 1)) * base_w * inv_zoom)
        py = int((event.y / max(self._canvas.winfo_height(), 1)) * base_h * inv_zoom)
        wx = px / base_w * self._map_size
        wy = self._map_size - py / base_h * self._map_size
        dialog = ctk.CTkInputDialog(text="Текст метки:", title="Метка на карте")
        text = dialog.get_input()
        if text:
            self._on_add_drawing(wx, wy, text)
