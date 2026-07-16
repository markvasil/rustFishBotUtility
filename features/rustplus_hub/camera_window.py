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
        *,
        status_text: str = "Подключение к камере...",
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
        try:
            self._win.attributes("-topmost", True)
        except Exception:
            pass

        bar = ctk.CTkFrame(self._win, fg_color="#141a28", height=36, corner_radius=0)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        self._title_label = ctk.CTkLabel(
            bar,
            text=self._title_text(),
            font=ctk.CTkFont(size=12),
            text_color="#8b93a7",
        )
        self._title_label.pack(side="left", padx=12)
        ctk.CTkButton(
            bar, text="✕", width=32, height=28, fg_color="#4a2230",
            command=self.close,
        ).pack(side="right", padx=8, pady=4)

        self._label = ctk.CTkLabel(
            self._win,
            text=status_text,
            text_color="#6b7280",
            font=ctk.CTkFont(size=12),
            width=self.DISPLAY_MAX[0],
            height=self.DISPLAY_MAX[1],
        )
        self._label.pack(padx=8, pady=8)

        win_w = self.DISPLAY_MAX[0] + 16
        win_h = self.DISPLAY_MAX[1] + 56
        x = max(40, (root.winfo_screenwidth() - win_w) // 2)
        y = max(40, (root.winfo_screenheight() - win_h) // 2)
        self._win.geometry(f"{win_w}x{win_h}+{x}+{y}")

        self._win.protocol("WM_DELETE_WINDOW", self.close)
        self._win.bind("<Escape>", lambda _e: self.close())
        self._win.bind("<KeyPress>", self._on_key_press)
        self._win.bind("<KeyRelease>", self._on_key_release)
        self._label.bind("<ButtonPress-1>", self._on_mouse_press)
        self._label.bind("<B1-Motion>", self._on_mouse_drag)
        self._label.bind("<ButtonRelease-1>", self._on_mouse_release)

        self._bring_to_front()
        self._win.after(80, self._bring_to_front)
        self._win.after(250, self._bring_to_front)

    def _title_text(self) -> str:
        hints = []
        if self._controls.get("movement"):
            hints.append("WASD/стрелки")
        if self._controls.get("mouse"):
            hints.append("мышь")
        hint_text = " | ".join(hints) if hints else "ожидание / статичная"
        return f"{self._camera_id} — {hint_text} | Esc — закрыть"

    def _bring_to_front(self) -> None:
        if self._closed or not self._win.winfo_exists():
            return
        try:
            self._win.deiconify()
            self._win.lift()
            self._win.attributes("-topmost", True)
            self._win.focus_force()
        except Exception:
            pass

    def set_controls(self, controls: Dict[str, bool]) -> None:
        self._controls = dict(controls or {})
        if self.is_open:
            self._title_label.configure(text=self._title_text())

    def set_status(self, text: str, *, error: bool = False) -> None:
        if not self.is_open:
            return
        color = "#f87171" if error else "#6b7280"
        self._label.configure(image=None, text=text, text_color=color)
        self._image_ref = None

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

    def close(self, *, notify_service: bool = True) -> None:
        if self._closed:
            return
        self._closed = True
        self._active_keys.clear()
        if notify_service:
            try:
                self._service.camera_clear_movement()
            except Exception:
                pass
            try:
                self._service.close_camera()
            except Exception:
                pass
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
