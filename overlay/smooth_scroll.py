from __future__ import annotations

import sys
from typing import Literal

import customtkinter as ctk


class SmoothScrollableFrame(ctk.CTkScrollableFrame):
    """CTkScrollableFrame с плавной прокруткой и инерцией колеса мыши."""

    TICK_MS = 12
    FRICTION = 0.90
    MIN_VELOCITY = 0.15
    MAX_VELOCITY = 72.0

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._vel_y = 0.0
        self._vel_x = 0.0
        self._scroll_job: str | None = None

    def destroy(self) -> None:
        self._cancel_scroll_job()
        super().destroy()

    def _cancel_scroll_job(self) -> None:
        if self._scroll_job is not None:
            try:
                self._parent_canvas.after_cancel(self._scroll_job)
            except Exception:
                pass
            self._scroll_job = None

    def _wheel_delta_units(self, event) -> float:
        if sys.platform.startswith("win"):
            return -float(event.delta) / 6.0
        if sys.platform == "darwin":
            return -float(event.delta)
        return -1.0 if getattr(event, "num", 0) == 4 else 1.0

    def _fraction_per_unit(self, axis: Literal["x", "y"]) -> float:
        bbox = self._parent_canvas.bbox("all")
        if not bbox:
            return 0.0
        if axis == "y":
            region = max(1.0, float(bbox[3] - bbox[1]))
            viewport = max(1.0, float(self._parent_canvas.winfo_height()))
            increment = float(self._parent_canvas.cget("yscrollincrement") or 1)
        else:
            region = max(1.0, float(bbox[2] - bbox[0]))
            viewport = max(1.0, float(self._parent_canvas.winfo_width()))
            increment = float(self._parent_canvas.cget("xscrollincrement") or 1)
        scrollable = max(0.0, region - viewport)
        if scrollable <= 0.0:
            return 0.0
        return increment / scrollable

    def _apply_axis_velocity(self, axis: Literal["x", "y"], velocity: float) -> float:
        if axis == "y":
            top, bottom = self._parent_canvas.yview()
        else:
            top, bottom = self._parent_canvas.xview()

        visible = bottom - top
        if visible >= 1.0:
            return 0.0

        frac_delta = velocity * self._fraction_per_unit(axis)
        new_top = top + frac_delta
        max_top = 1.0 - visible

        if new_top <= 0.0:
            new_top = 0.0
            velocity = 0.0
        elif new_top >= max_top:
            new_top = max_top
            velocity = 0.0

        if new_top != top:
            if axis == "y":
                self._parent_canvas.yview_moveto(new_top)
            else:
                self._parent_canvas.xview_moveto(new_top)
        return velocity

    def _tick_scroll(self) -> None:
        self._scroll_job = None
        if abs(self._vel_y) >= self.MIN_VELOCITY:
            self._vel_y = self._apply_axis_velocity("y", self._vel_y) * self.FRICTION
        else:
            self._vel_y = 0.0

        if abs(self._vel_x) >= self.MIN_VELOCITY:
            self._vel_x = self._apply_axis_velocity("x", self._vel_x) * self.FRICTION
        else:
            self._vel_x = 0.0

        if abs(self._vel_y) >= self.MIN_VELOCITY or abs(self._vel_x) >= self.MIN_VELOCITY:
            self._scroll_job = self._parent_canvas.after(self.TICK_MS, self._tick_scroll)

    def _kick_scroll_animation(self) -> None:
        if self._scroll_job is None:
            self._tick_scroll()

    def _add_velocity(self, axis: Literal["x", "y"], delta: float) -> None:
        if axis == "y":
            self._vel_y = max(-self.MAX_VELOCITY, min(self.MAX_VELOCITY, self._vel_y + delta))
        else:
            self._vel_x = max(-self.MAX_VELOCITY, min(self.MAX_VELOCITY, self._vel_x + delta))
        self._kick_scroll_animation()

    def _mouse_wheel_all(self, event) -> None:
        if not self._check_if_valid_scroll(event.widget):
            return

        delta = self._wheel_delta_units(event)
        if delta == 0.0:
            return

        if self._shift_pressed and self._orientation == "vertical":
            view = self._parent_canvas.xview()
            if view == (0.0, 1.0):
                return
            self._add_velocity("x", delta)
            return

        if self._orientation == "horizontal":
            view = self._parent_canvas.xview()
            if view == (0.0, 1.0):
                return
            self._add_velocity("x", delta)
            return

        view = self._parent_canvas.yview()
        if view == (0.0, 1.0):
            return
        self._add_velocity("y", delta)
