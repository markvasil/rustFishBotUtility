from __future__ import annotations

import ctypes
import tkinter as tk
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

import customtkinter as ctk

from features.genetics.calibration import RegionCalibration
from features.genetics.scanner import (
    calibrated_slot_rects,
    find_rust_window_capture_area,
    get_regions_for_frame,
    resolve_profile,
    search_rect_from_slots,
)

SlotRect = Tuple[int, int, int, int]


@dataclass(frozen=True)
class LocalRect:
    x1: int
    y1: int
    x2: int
    y2: int


@dataclass(frozen=True)
class RegionDrawInfo:
    region_id: str
    label: str
    color: str
    search_zone: LocalRect
    gene_slots: Tuple[LocalRect, ...]


REGION_COLORS = {
    "planter": "#66ff66",
    "inventory": "#ff6666",
}


def _rect_from_tuple(rect: SlotRect) -> LocalRect:
    return LocalRect(rect[0], rect[1], rect[2], rect[3])


def build_region_draw_info_for_size(
    width: int,
    height: int,
    region_ids: List[str],
    profile_id: Optional[str] = None,
    calibrations: Optional[Dict[str, RegionCalibration]] = None,
) -> List[RegionDrawInfo]:
    profile = resolve_profile(width, height, profile_id)
    regions = get_regions_for_frame(width, height, profile.id)
    calibrations = calibrations or {}
    items: List[RegionDrawInfo] = []

    for region_id in region_ids:
        region = regions.get(region_id)
        if region is None:
            continue

        cal = calibrations.get(region_id, RegionCalibration())
        slot_rects = calibrated_slot_rects(width, height, region, cal)
        sx1, sy1, sx2, sy2 = search_rect_from_slots(slot_rects)

        items.append(
            RegionDrawInfo(
                region_id=region.id,
                label=region.label,
                color=REGION_COLORS.get(region.id, "#ffffff"),
                search_zone=LocalRect(sx1, sy1, sx2, sy2),
                gene_slots=tuple(_rect_from_tuple(rect) for rect in slot_rects),
            )
        )

    return items


class ScanPreviewWindow:
    """Оверлей зон сканирования с калибровкой каждого слота 1–6."""

    REFRESH_MS = 250

    def __init__(
        self,
        root: ctk.CTk,
        on_calibration_saved: Optional[Callable[[Dict[str, RegionCalibration]], None]] = None,
    ) -> None:
        self._root = root
        self._on_calibration_saved = on_calibration_saved
        self._win: Optional[tk.Toplevel] = None
        self._canvas: Optional[tk.Canvas] = None
        self._visible = False
        self._edit_mode = False
        self._region_ids: List[str] = ["inventory"]
        self._profile_id: Optional[str] = None
        self._calibrations: Dict[str, RegionCalibration] = {}
        self._refresh_job: Optional[str] = None
        self._drag_target: Optional[Tuple[str, int]] = None
        self._drag_anchor: Optional[Tuple[int, int, int, int]] = None
        self._frame_size: Tuple[int, int] = (1920, 1080)
        self._screen_origin: Tuple[int, int] = (0, 0)
        self._drag_visual_job: Optional[str] = None

    @property
    def is_visible(self) -> bool:
        return self._visible and self._win is not None and self._win.winfo_exists()

    @property
    def is_calibrating(self) -> bool:
        return self._visible and self._edit_mode

    def get_calibrations(self) -> Dict[str, RegionCalibration]:
        return {key: RegionCalibration(cal.dx, cal.dy, cal.slots) for key, cal in self._calibrations.items()}

    def set_calibrations(self, calibrations: Dict[str, RegionCalibration]) -> None:
        self._calibrations = {
            key: RegionCalibration(cal.dx, cal.dy, cal.slots)
            for key, cal in calibrations.items()
        }

    def configure(self, region_ids: List[str], profile_id: Optional[str]) -> None:
        self._region_ids = region_ids
        mapping = {"Авто": None, "1080p": "1080p", "2K": "1440p"}
        self._profile_id = mapping.get(profile_id or "", profile_id)

    def show_calibration(
        self,
        region_ids: Optional[List[str]] = None,
        profile_id: Optional[str] = None,
        calibrations: Optional[Dict[str, RegionCalibration]] = None,
    ) -> None:
        self._edit_mode = True
        if calibrations is not None:
            self.set_calibrations(calibrations)
        self._ensure_window()
        self.show(region_ids, profile_id)

    def show_monitoring(
        self,
        region_ids: Optional[List[str]] = None,
        profile_id: Optional[str] = None,
        calibrations: Optional[Dict[str, RegionCalibration]] = None,
    ) -> None:
        self._edit_mode = False
        if calibrations is not None:
            self.set_calibrations(calibrations)
        self._ensure_window()
        self.show(region_ids, profile_id)

    def finish_calibration(self) -> Dict[str, RegionCalibration]:
        self._edit_mode = False
        self._drag_target = None
        self._drag_anchor = None
        self._unbind_canvas_drag()
        if self._on_calibration_saved:
            self._on_calibration_saved(self.get_calibrations())
        if self.is_visible:
            self._redraw()
        return self.get_calibrations()

    def show(self, region_ids: Optional[List[str]] = None, profile_id: Optional[str] = None) -> None:
        if region_ids is not None:
            self._region_ids = region_ids
        if profile_id is not None:
            self.configure(self._region_ids, profile_id)

        self._ensure_window()
        self._win.deiconify()
        self._win.lift()
        self._visible = True
        self._redraw()
        self._schedule_refresh()

    def hide(self) -> None:
        self._visible = False
        self._edit_mode = False
        self._drag_target = None
        self._drag_anchor = None
        self._unbind_canvas_drag()
        if self._drag_visual_job:
            self._root.after_cancel(self._drag_visual_job)
            self._drag_visual_job = None
        if self._refresh_job:
            self._root.after_cancel(self._refresh_job)
            self._refresh_job = None
        if self._win and self._win.winfo_exists():
            self._win.withdraw()

    def destroy(self) -> None:
        self.hide()
        if self._win and self._win.winfo_exists():
            self._win.destroy()
        self._win = None
        self._canvas = None

    def _ensure_window(self) -> None:
        if self._win is not None and self._win.winfo_exists():
            return

        self._win = tk.Toplevel(self._root)
        self._win.overrideredirect(True)
        self._win.attributes("-topmost", True)
        self._win.attributes("-transparentcolor", "#010101")
        self._win.configure(bg="#010101")
        self._canvas = tk.Canvas(self._win, bg="#010101", highlightthickness=0, bd=0)
        self._canvas.pack(fill="both", expand=True)

    def _set_click_through(self, enabled: bool) -> None:
        if not self._win:
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(self._win.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            style |= 0x00080000
            if enabled:
                style |= 0x00000020
            else:
                style &= ~0x00000020
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, style)
        except Exception:
            pass

    def _bind_canvas_drag(self) -> None:
        if not self._canvas:
            return
        self._canvas.bind("<Button-1>", self._on_canvas_down)
        self._canvas.bind("<B1-Motion>", self._on_canvas_move)
        self._canvas.bind("<ButtonRelease-1>", self._on_canvas_up)

    def _unbind_canvas_drag(self) -> None:
        if not self._canvas:
            return
        self._canvas.unbind("<Button-1>")
        self._canvas.unbind("<B1-Motion>")
        self._canvas.unbind("<ButtonRelease-1>")

    def _hit_test_slot(self, x: int, y: int) -> Optional[Tuple[str, int]]:
        for overlay in self._current_overlays():
            for index, slot in enumerate(overlay.gene_slots):
                if slot.x1 <= x <= slot.x2 and slot.y1 <= y <= slot.y2:
                    return overlay.region_id, index
        return None

    def _draw_calibration_overlay(self, overlays: List[RegionDrawInfo]) -> None:
        if not self._canvas:
            return

        self._canvas.delete("cal_overlay")
        for overlay in overlays:
            search = overlay.search_zone
            self._canvas.create_rectangle(
                search.x1,
                search.y1,
                search.x2,
                search.y2,
                outline=overlay.color,
                dash=(6, 4),
                width=2,
                tags="cal_overlay",
            )
            self._canvas.create_text(
                search.x1 + 6,
                max(4, search.y1 - 18),
                anchor="nw",
                fill=overlay.color,
                font=("Segoe UI", 10, "bold"),
                text=f"{overlay.label}",
                tags="cal_overlay",
            )

            for index, slot in enumerate(overlay.gene_slots, start=1):
                active = (
                    self._drag_target
                    and self._drag_target[0] == overlay.region_id
                    and (
                        self._drag_target[1] == index - 1
                        or self._drag_target[1] == -1
                    )
                )
                self._canvas.create_rectangle(
                    slot.x1,
                    slot.y1,
                    slot.x2,
                    slot.y2,
                    outline=overlay.color,
                    fill=overlay.color if active else "",
                    stipple="gray25" if active else "",
                    width=3,
                    tags="cal_overlay",
                )
                self._canvas.create_text(
                    (slot.x1 + slot.x2) // 2,
                    (slot.y1 + slot.y2) // 2,
                    fill="#ffffff" if active else overlay.color,
                    font=("Segoe UI", 10, "bold"),
                    text=str(index),
                    tags="cal_overlay",
                )

    def _schedule_drag_visuals(self) -> None:
        if self._drag_visual_job:
            self._root.after_cancel(self._drag_visual_job)
        self._drag_visual_job = self._root.after_idle(self._run_drag_visuals)

    def _run_drag_visuals(self) -> None:
        self._drag_visual_job = None
        self._update_drag_visuals()

    def _update_drag_visuals(self) -> None:
        if not self._canvas or not self._edit_mode:
            return

        overlays = self._current_overlays()
        self._draw_calibration_overlay(overlays)

        if self._win and self._win.winfo_exists():
            self._win.update_idletasks()

    def _schedule_refresh(self) -> None:
        if self._refresh_job:
            self._root.after_cancel(self._refresh_job)
        if self._visible and not self._edit_mode:
            self._refresh_job = self._root.after(self.REFRESH_MS, self._refresh_tick)

    def _refresh_tick(self) -> None:
        if self._visible and not self._edit_mode:
            self._redraw()
            self._schedule_refresh()

    def _resolve_capture_geometry(self) -> Tuple[int, int, int, int]:
        capture = find_rust_window_capture_area()
        if capture:
            return capture["left"], capture["top"], capture["width"], capture["height"]

        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        return 0, 0, sw, sh

    def _current_overlays(self) -> List[RegionDrawInfo]:
        width, height = self._frame_size
        profile = resolve_profile(width, height, self._profile_id)
        return build_region_draw_info_for_size(
            width,
            height,
            self._region_ids,
            profile.id,
            self._calibrations,
        )

    def _on_canvas_down(self, event: tk.Event) -> None:
        if not self._edit_mode:
            return

        hit = self._hit_test_slot(event.x, event.y)
        if hit is None:
            return

        region_id, slot_index = hit
        shift = bool(event.state & 0x0001)
        cal = self._calibrations.setdefault(region_id, RegionCalibration())

        if shift:
            self._drag_target = (region_id, -1)
            self._drag_anchor = (event.x_root, event.y_root, cal.dx, cal.dy)
            return

        slot_dx, slot_dy = cal.slots[slot_index]
        self._drag_target = (region_id, slot_index)
        self._drag_anchor = (event.x_root, event.y_root, slot_dx, slot_dy)

    def _on_canvas_move(self, event: tk.Event) -> None:
        if not self._edit_mode or not self._drag_target or not self._drag_anchor:
            return

        region_id, slot_index = self._drag_target
        ax, ay, dx0, dy0 = self._drag_anchor
        cal = self._calibrations.setdefault(region_id, RegionCalibration())
        delta_x = event.x_root - ax
        delta_y = event.y_root - ay

        if slot_index < 0:
            self._calibrations[region_id] = RegionCalibration(
                dx0 + delta_x,
                dy0 + delta_y,
                cal.slots,
            )
        else:
            slots = list(cal.slots)
            slots[slot_index] = (dx0 + delta_x, dy0 + delta_y)
            self._calibrations[region_id] = RegionCalibration(cal.dx, cal.dy, tuple(slots))

        self._schedule_drag_visuals()

    def _on_canvas_up(self, _event: tk.Event) -> None:
        if not self._drag_target:
            return

        self._drag_target = None
        self._drag_anchor = None
        if self._edit_mode:
            self._update_drag_visuals()

    def _redraw(self) -> None:
        if not self._canvas or not self._win or not self._win.winfo_exists():
            return

        left, top, width, height = self._resolve_capture_geometry()
        self._frame_size = (width, height)
        self._screen_origin = (left, top)
        self._win.geometry(f"{width}x{height}+{left}+{top}")
        self._canvas.config(width=width, height=height)
        self._canvas.delete("all")

        profile = resolve_profile(width, height, self._profile_id)
        overlays = build_region_draw_info_for_size(
            width,
            height,
            self._region_ids,
            profile.id,
            self._calibrations,
        )

        if self._edit_mode:
            self._set_click_through(False)
            self._bind_canvas_drag()
            title = f"Калибровка · {profile.label} · двигайте рамки 1–6"
            hint = "ЛКМ на рамке — двигать. Shift+ЛКМ — все 6 вместе. Готово — вернуть клики в Rust"
            self._draw_calibration_overlay(overlays)
        else:
            self._set_click_through(True)
            self._unbind_canvas_drag()
            title = f"Сканер · {profile.label} · {width}×{height}"
            hint = "Пунктир — зона поиска, цифры — слоты генов"

        self._canvas.create_text(
            12,
            12,
            anchor="nw",
            fill="#ffffff",
            font=("Segoe UI", 11, "bold"),
            text=title,
        )
        self._canvas.create_text(
            12,
            30,
            anchor="nw",
            fill="#cccccc",
            font=("Segoe UI", 9),
            text=hint,
        )

        if not self._edit_mode:
            for overlay in overlays:
                search = overlay.search_zone
                self._canvas.create_rectangle(
                    search.x1,
                    search.y1,
                    search.x2,
                    search.y2,
                    outline=overlay.color,
                    dash=(6, 4),
                    width=2,
                )

                for index, slot in enumerate(overlay.gene_slots, start=1):
                    self._canvas.create_rectangle(
                        slot.x1,
                        slot.y1,
                        slot.x2,
                        slot.y2,
                        outline=overlay.color,
                        width=2,
                    )
                    self._canvas.create_text(
                        (slot.x1 + slot.x2) // 2,
                        (slot.y1 + slot.y2) // 2,
                        fill=overlay.color,
                        font=("Segoe UI", 8, "bold"),
                        text=str(index),
                    )

                self._canvas.create_text(
                    search.x1 + 6,
                    max(4, search.y1 - 18),
                    anchor="nw",
                    fill=overlay.color,
                    font=("Segoe UI", 10, "bold"),
                    text=f"{overlay.label}",
                )
