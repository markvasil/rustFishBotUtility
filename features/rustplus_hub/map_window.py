from __future__ import annotations

import tkinter as tk
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import customtkinter as ctk
from PIL import Image, ImageTk

from services.rustplus.live_format import has_active_motion, project_motion
from services.rustplus.map_renderer import MapRenderer


class MapWindow:
    """Интерактивная карта: zoom/pan, follow, event tracking, рисование."""

    TICK_MS = 100
    ZOOM_STEP = 0.2
    ZOOM_MIN = 1.0
    ZOOM_MAX = 4.0
    # Запас вокруг viewport: pan без чёрных полос, пока не съели margin.
    PAN_TILE_FACTOR = 2.5

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
        # После ручного pan камера не прилипает к follow, пока не сменят цель.
        self._follow_camera = bool(follow_steam_id)
        self._on_close = on_close
        self._on_track_event = on_track_event
        self._on_add_drawing = on_add_drawing
        self._renderer = renderer or MapRenderer()
        self._zoom = 1.0
        self._view_cx: Optional[float] = None
        self._view_cy: Optional[float] = None
        self._drag_last: Optional[tuple[int, int]] = None
        self._press_pos: Optional[tuple[int, int]] = None
        self._dragging = False
        self._photo: Optional[ImageTk.PhotoImage] = None
        self._image_id: Optional[int] = None
        self._tile_x = 0.0
        self._tile_y = 0.0
        self._tile_w = 0
        self._tile_h = 0
        self._tick_job: Optional[str] = None
        self._rebuild_job: Optional[str] = None
        self._dirty = True
        self._rendering = False
        self._base_size: Optional[tuple[int, int]] = None
        self._last_canvas_size: tuple[int, int] = (0, 0)
        self._composite: Optional[Image.Image] = None
        self._composite_dirty = True

        self._win = ctk.CTkToplevel(root)
        self._win.title("Rust+ — карта сервера")
        self._win.configure(fg_color="#0d1117")
        self._win.attributes("-topmost", True)

        bar = ctk.CTkFrame(self._win, fg_color="#141a28", height=40, corner_radius=0)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        ctk.CTkLabel(
            bar,
            text="Колесо — зум | ЛКМ — двигать карту | клик по событию — трек | ПКМ — метка | Esc — закрыть",
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
        self._canvas.bind("<Enter>", lambda _e: self._canvas.focus_set())
        self._canvas.bind("<MouseWheel>", self._on_mousewheel)
        self._canvas.bind("<Button-4>", self._on_mousewheel)
        self._canvas.bind("<Button-5>", self._on_mousewheel)
        self._win.focus_force()
        self._canvas.focus_set()
        self._mark_dirty()
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
        self._composite_dirty = True

    def _base_dimensions(self) -> tuple[int, int]:
        if self._base_size is None:
            self._base_size = self._renderer.get_base_size(self._path)
        return self._base_size

    def _ensure_view_center(self) -> tuple[float, float]:
        base_w, base_h = self._base_dimensions()
        if self._view_cx is None or self._view_cy is None:
            self._view_cx = base_w / 2.0
            self._view_cy = base_h / 2.0
        return float(self._view_cx), float(self._view_cy)

    def _clamp_view_center(self) -> None:
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
            prev = self._follow_steam_id
            self._follow_steam_id = follow_steam_id
            if follow_steam_id != prev:
                self._follow_camera = True
        if map_size:
            self._map_size = map_size
        self._mark_dirty()

    def close(self) -> None:
        for job_name in ("_tick_job", "_rebuild_job"):
            job = getattr(self, job_name, None)
            if job:
                try:
                    self._win.after_cancel(job)
                except Exception:
                    pass
                setattr(self, job_name, None)
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
                if self._follow_camera and self._follow_steam_id:
                    self._apply_follow_to_view()
                if self._follow_steam_id or self._dirty or self._has_moving_overlay():
                    if not self._dragging:
                        self._composite_dirty = True
                        self._request_rebuild()
                    else:
                        self._composite_dirty = True
                self._tick_job = self._win.after(self.TICK_MS, tick)
        self._tick_job = self._win.after(self.TICK_MS, tick)

    def _apply_follow_to_view(self) -> None:
        if not self._follow_steam_id or not self._map_size or self._dragging:
            return
        projected_team = project_motion(self._team, map_size=self._map_size)
        base_w, base_h = self._base_dimensions()
        for member in projected_team:
            if int(member.get("steam_id", 0)) == int(self._follow_steam_id):
                from services.rustplus.live_format import world_to_map_pixel

                px, py = world_to_map_pixel(
                    float(member["x"]), float(member["y"]), self._map_size, base_w, base_h,
                )
                self._view_cx, self._view_cy = float(px), float(py)
                self._clamp_view_center()
                break

    def _on_canvas_configure(self, event) -> None:
        if event.width < 50 or event.height < 50:
            return
        size = (int(event.width), int(event.height))
        if size == self._last_canvas_size:
            return
        self._last_canvas_size = size
        self._dirty = True
        self._request_rebuild()

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
        self._rebuild_view()

    def _rebuild_composite(self) -> Optional[Image.Image]:
        """Полная карта с оверлеями. Камеру (_view_*) не трогает."""
        projected_team = project_motion(self._team, map_size=self._map_size)
        projected_events = project_motion(self._events, map_size=self._map_size)
        projected_vendors = project_motion(self._vendors, map_size=self._map_size)
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
            view_center=None,
            zoom=1.0,
            output_size=None,
        )
        if image.mode != "RGB":
            image = image.convert("RGB")
        self._composite = image
        self._composite_dirty = False
        self._base_size = image.size
        return image

    def _request_rebuild(self) -> None:
        if self._rebuild_job is not None:
            return

        def flush() -> None:
            self._rebuild_job = None
            self._rebuild_view()

        self._rebuild_job = self._win.after_idle(flush)

    def _rebuild_view(self) -> None:
        """Пересобрать видимый кадр под текущий _view_* / _zoom."""
        if not self.is_open or self._rendering:
            self._request_rebuild()
            return
        if self._dragging:
            return
        cw = int(self._canvas.winfo_width())
        ch = int(self._canvas.winfo_height())
        if cw < 50 or ch < 50:
            return
        self._rendering = True
        try:
            if self._composite_dirty or self._composite is None:
                self._rebuild_composite()
            self._blit_tile(cw, ch)
            self._dirty = False
        finally:
            self._rendering = False

    def _blit_tile(self, cw: Optional[int] = None, ch: Optional[int] = None) -> None:
        """Оверсайз-тайл вокруг _view_*: центр вида = центр окна."""
        composite = self._composite
        if composite is None:
            return
        if cw is None:
            cw = int(self._canvas.winfo_width())
        if ch is None:
            ch = int(self._canvas.winfo_height())
        if cw < 50 or ch < 50:
            return
        center = self._ensure_view_center()
        image, origin = self._build_pan_tile(composite, center, self._zoom, (cw, ch))
        self._photo = ImageTk.PhotoImage(image)
        self._canvas.delete("all")
        self._tile_x = float(origin[0])
        self._tile_y = float(origin[1])
        self._tile_w = int(image.size[0])
        self._tile_h = int(image.size[1])
        self._image_id = self._canvas.create_image(
            int(round(self._tile_x)),
            int(round(self._tile_y)),
            anchor="nw",
            image=self._photo,
        )

    def _build_pan_tile(
        self,
        composite: Image.Image,
        center: Tuple[float, float],
        zoom: float,
        canvas_size: Tuple[int, int],
    ) -> tuple[Image.Image, tuple[float, float]]:
        """Тайл ≥ viewport. Origin ставит center в середину окна (не центр тайла)."""
        w, h = composite.size
        cw, ch = canvas_size
        if zoom <= 1.0:
            return composite.resize((cw, ch), Image.Resampling.BILINEAR), (0.0, 0.0)

        view_w = w / zoom
        view_h = h / zoom
        factor = min(self.PAN_TILE_FACTOR, w / max(view_w, 1.0), h / max(view_h, 1.0))
        factor = max(1.0, factor)
        crop_w = max(1, min(w, int(round(view_w * factor))))
        crop_h = max(1, min(h, int(round(view_h * factor))))
        cx, cy = center
        left = max(0, min(int(round(cx - crop_w / 2.0)), w - crop_w))
        top = max(0, min(int(round(cy - crop_h / 2.0)), h - crop_h))
        cropped = composite.crop((left, top, left + crop_w, top + crop_h))

        scale_x = cw / view_w
        scale_y = ch / view_h
        tile_w = max(cw, int(round(crop_w * scale_x)))
        tile_h = max(ch, int(round(crop_h * scale_y)))
        tile = cropped.resize((tile_w, tile_h), Image.Resampling.BILINEAR)

        # Точка (cx,cy) карты → пиксель тайла → должна попасть в центр canvas.
        anchor_x = (cx - left) * scale_x
        anchor_y = (cy - top) * scale_y
        origin_x = cw / 2.0 - anchor_x
        origin_y = ch / 2.0 - anchor_y
        return tile, (origin_x, origin_y)

    def _tile_covers_canvas(self, cw: int, ch: int) -> bool:
        if self._tile_w <= 0 or self._tile_h <= 0:
            return False
        return (
            self._tile_x <= 1.0
            and self._tile_y <= 1.0
            and self._tile_x + self._tile_w >= cw - 1
            and self._tile_y + self._tile_h >= ch - 1
        )

    def _change_zoom(self, direction: int, anchor_canvas: Optional[tuple[int, int]] = None) -> None:
        old_zoom = self._zoom
        if direction > 0:
            new_zoom = min(self.ZOOM_MAX, old_zoom + self.ZOOM_STEP)
        else:
            new_zoom = max(self.ZOOM_MIN, old_zoom - self.ZOOM_STEP)
        if abs(new_zoom - old_zoom) < 1e-6:
            return

        cw = max(int(self._canvas.winfo_width()), 1)
        ch = max(int(self._canvas.winfo_height()), 1)
        if anchor_canvas is None:
            anchor_canvas = (cw // 2, ch // 2)
        ax, ay = anchor_canvas
        bx, by = self._canvas_to_base(ax, ay)
        self._zoom = new_zoom
        if new_zoom <= 1.0:
            self._zoom = 1.0
            self._clamp_view_center()
            self._request_rebuild()
            return

        base_w, base_h = self._base_dimensions()
        crop_w = base_w / new_zoom
        crop_h = base_h / new_zoom
        fx = ax / cw
        fy = ay / ch
        self._view_cx = bx - fx * crop_w + crop_w / 2.0
        self._view_cy = by - fy * crop_h + crop_h / 2.0
        self._clamp_view_center()
        self._request_rebuild()

    def _on_mousewheel(self, event) -> None:
        delta = getattr(event, "delta", 0) or 0
        num = getattr(event, "num", 0) or 0
        if delta > 0 or num == 4:
            direction = 1
        elif delta < 0 or num == 5:
            direction = -1
        else:
            return
        self._change_zoom(direction, (int(event.x), int(event.y)))
        return "break"

    def _on_press(self, event) -> None:
        self._press_pos = (event.x, event.y)
        self._drag_last = (event.x, event.y)
        self._dragging = False

    def _on_drag(self, event) -> None:
        if not self._drag_last:
            return
        if self._zoom <= 1.0:
            self._drag_last = (event.x, event.y)
            return
        dx = event.x - self._drag_last[0]
        dy = event.y - self._drag_last[1]
        self._drag_last = (event.x, event.y)
        if dx == 0 and dy == 0:
            return

        self._dragging = True
        self._follow_camera = False

        base_w, base_h = self._base_dimensions()
        cw = max(int(self._canvas.winfo_width()), 1)
        ch = max(int(self._canvas.winfo_height()), 1)
        crop_w = base_w / self._zoom
        crop_h = base_h / self._zoom

        cx0, cy0 = self._ensure_view_center()
        self._view_cx = cx0 - dx * (crop_w / cw)
        self._view_cy = cy0 - dy * (crop_h / ch)
        self._clamp_view_center()
        cx1, cy1 = self._ensure_view_center()

        # Двигаем картинку ровно на величину, которую принял clamp.
        move_x = (cx0 - cx1) * (cw / crop_w)
        move_y = (cy0 - cy1) * (ch / crop_h)
        if abs(move_x) < 1e-6 and abs(move_y) < 1e-6:
            return
        self._tile_x += move_x
        self._tile_y += move_y
        if self._image_id is not None:
            self._canvas.move(self._image_id, move_x, move_y)

        # Запас тайла кончился — подтянуть новый кусок карты без отпускания ЛКМ.
        if not self._tile_covers_canvas(cw, ch) and self._composite is not None:
            self._blit_tile(cw, ch)

    def _on_release(self, event) -> None:
        press = self._press_pos
        was_dragging = self._dragging
        self._press_pos = None
        self._drag_last = None
        self._dragging = False
        if was_dragging:
            if self._composite is None or self._composite_dirty:
                self._request_rebuild()
            else:
                self._blit_tile()
        if not press or not self._map_size:
            return
        moved = abs(event.x - press[0]) + abs(event.y - press[1])
        if moved > 6:
            return
        self._try_track_event(event.x, event.y)

    def _canvas_to_base(self, canvas_x: int, canvas_y: int) -> tuple[float, float]:
        """Пиксели окна → пиксели базовой карты."""
        base_w, base_h = self._base_dimensions()
        cw = max(int(self._canvas.winfo_width()), 1)
        ch = max(int(self._canvas.winfo_height()), 1)
        if self._zoom <= 1.0:
            return canvas_x / cw * base_w, canvas_y / ch * base_h

        cx, cy = self._ensure_view_center()
        crop_w = base_w / self._zoom
        crop_h = base_h / self._zoom
        # Во время drag картинка смещена; _view_* уже включает pan.
        left = cx - crop_w / 2.0
        top = cy - crop_h / 2.0
        return left + canvas_x / cw * crop_w, top + canvas_y / ch * crop_h

    def _try_track_event(self, cx: int, cy: int) -> None:
        from services.rustplus.live_format import world_to_map_pixel

        base_w, base_h = self._base_dimensions()
        click_x, click_y = self._canvas_to_base(cx, cy)
        best = None
        best_dist = 9999.0
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
            self._request_rebuild()

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
