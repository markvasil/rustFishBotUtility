from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Dict, Optional, Set

import customtkinter as ctk
from PIL import Image
from rustplus.remote.camera.camera_constants import MovementControls

if TYPE_CHECKING:
    from services.rustplus.service import RustPlusService


class CameraWindow:
    """Окно просмотра CCTV / PTZ камеры с управлением."""

    DISPLAY_MAX = (640, 480)
    KEY_BINDINGS = {
        "w": MovementControls.FORWARD,
        "s": MovementControls.BACKWARD,
        "a": MovementControls.LEFT,
        "d": MovementControls.RIGHT,
        "Up": MovementControls.FORWARD,
        "Down": MovementControls.BACKWARD,
        "Left": MovementControls.LEFT,
        "Right": MovementControls.RIGHT,
    }

    def __init__(
        self,
        root: ctk.CTk,
        service: "RustPlusService",
        camera_id: str,
        controls: Optional[Dict[str, bool]] = None,
    ) -> None:
        self._root = root
        self._service = service
        self._camera_id = camera_id
        self._controls = controls or {}
        self._image_ref: Optional[ctk.CTkImage] = None
        self._active_keys: Set[int] = set()
        self._last_mouse: Optional[tuple[int, int]] = None
        self._closed = False

        self._win = ctk.CTkToplevel(root)
        self._win.title(f"Rust+ — {camera_id}")
        self._win.configure(fg_color="#0d1117")
        self._win.attributes("-topmost", True)

        bar = ctk.CTkFrame(self._win, fg_color="#141a28", height=36, corner_radius=0)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        hints = []
        if self._controls.get("movement"):
            hints.append("WASD/стрелки")
        if self._controls.get("mouse"):
            hints.append("мышь")
        hint_text = " | ".join(hints) if hints else "Статичная камера"
        ctk.CTkLabel(
            bar,
            text=f"{camera_id} — {hint_text} | Esc — закрыть",
            font=ctk.CTkFont(size=12),
            text_color="#8b93a7",
        ).pack(side="left", padx=12)
        ctk.CTkButton(
            bar, text="✕", width=32, height=28, fg_color="#4a2230",
            command=self.close,
        ).pack(side="right", padx=8, pady=4)

        self._label = ctk.CTkLabel(
            self._win,
            text="Ожидание кадра...",
            text_color="#6b7280",
            font=ctk.CTkFont(size=12),
        )
        self._label.pack(padx=8, pady=8)

        win_w = self.DISPLAY_MAX[0] + 16
        win_h = self.DISPLAY_MAX[1] + 56
        x = (root.winfo_screenwidth() - win_w) // 2
        y = (root.winfo_screenheight() - win_h) // 2
        self._win.geometry(f"{win_w}x{win_h}+{x}+{y}")

        self._win.protocol("WM_DELETE_WINDOW", self.close)
        self._win.bind("<Escape>", lambda _e: self.close())
        self._win.bind("<KeyPress>", self._on_key_press)
        self._win.bind("<KeyRelease>", self._on_key_release)
        self._label.bind("<ButtonPress-1>", self._on_mouse_press)
        self._label.bind("<B1-Motion>", self._on_mouse_drag)
        self._label.bind("<ButtonRelease-1>", self._on_mouse_release)
        self._win.focus_force()

    @property
    def is_open(self) -> bool:
        return not self._closed and self._win.winfo_exists()

    def update_frame(self, image_path: str | Path) -> None:
        if not self.is_open:
            return
        try:
            image = Image.open(image_path)
            if image.mode != "RGB":
                image = image.convert("RGB")
            image.thumbnail(self.DISPLAY_MAX, Image.Resampling.LANCZOS)
            self._image_ref = ctk.CTkImage(
                light_image=image, dark_image=image, size=image.size,
            )
            self._label.configure(image=self._image_ref, text="")
        except Exception as exc:
            self._label.configure(image=None, text=str(exc), text_color="#f87171")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._active_keys.clear()
        self._service.camera_clear_movement()
        self._service.close_camera()
        if self._win.winfo_exists():
            self._win.destroy()

    def _on_key_press(self, event) -> None:
        if not self._controls.get("movement"):
            return
        movement = self.KEY_BINDINGS.get(event.keysym)
        if movement is None:
            return
        if movement in self._active_keys:
            return
        self._active_keys.add(movement)
        self._service.camera_move(*self._active_keys)

    def _on_key_release(self, event) -> None:
        if not self._controls.get("movement"):
            return
        movement = self.KEY_BINDINGS.get(event.keysym)
        if movement is None:
            return
        self._active_keys.discard(movement)
        if self._active_keys:
            self._service.camera_move(*self._active_keys)
        else:
            self._service.camera_clear_movement()

    def _on_mouse_press(self, event) -> None:
        if self._controls.get("mouse"):
            self._last_mouse = (event.x, event.y)

    def _on_mouse_drag(self, event) -> None:
        if not self._controls.get("mouse") or self._last_mouse is None:
            return
        dx = event.x - self._last_mouse[0]
        dy = event.y - self._last_mouse[1]
        self._last_mouse = (event.x, event.y)
        if dx or dy:
            self._service.camera_look(float(dx) * 0.15, float(dy) * 0.15)

    def _on_mouse_release(self, _event) -> None:
        self._last_mouse = None
