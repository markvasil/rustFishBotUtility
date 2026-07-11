from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk


class Theme:
    BG = "#0d1117"
    SURFACE = "#141a28"
    CARD = "#151b28"
    CARD_ALT = "#1a2236"
    BORDER = "#243044"
    ACCENT = "#e07a3a"
    ACCENT_DARK = "#c45c26"
    TEXT = "#e8ecf4"
    MUTED = "#9aa3b5"
    DIM = "#6b7280"
    SUCCESS = "#4ade80"
    WARN = "#fbbf24"
    ERROR = "#f87171"
    INFO = "#6ec1e4"
    PANEL = "#10151f"


def card(parent, *, alt: bool = False, **kwargs) -> ctk.CTkFrame:
    return ctk.CTkFrame(
        parent,
        fg_color=Theme.CARD_ALT if alt else Theme.CARD,
        corner_radius=12,
        border_width=1,
        border_color=Theme.BORDER,
        **kwargs,
    )


def section_header(
    parent,
    title: str,
    subtitle: Optional[str] = None,
    *,
    action_text: Optional[str] = None,
    action_command: Optional[Callable[[], None]] = None,
) -> ctk.CTkFrame:
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", padx=4, pady=(10, 6))
    left = ctk.CTkFrame(row, fg_color="transparent")
    left.pack(side="left", fill="x", expand=True)
    ctk.CTkLabel(
        left,
        text=title,
        font=ctk.CTkFont(size=13, weight="bold"),
        text_color=Theme.TEXT,
        anchor="w",
    ).pack(anchor="w")
    if subtitle:
        ctk.CTkLabel(
            left,
            text=subtitle,
            font=ctk.CTkFont(size=10),
            text_color=Theme.DIM,
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))
    if action_text and action_command:
        btn_secondary(row, action_text, action_command, width=110, height=26).pack(side="right")
    return row


def step_card(parent, step: int, title: str, body_builder: Callable[[ctk.CTkFrame], None]) -> None:
    frame = card(parent)
    frame.pack(fill="x", padx=4, pady=(0, 8))
    head = ctk.CTkFrame(frame, fg_color="transparent")
    head.pack(fill="x", padx=12, pady=(10, 6))
    badge = ctk.CTkLabel(
        head,
        text=str(step),
        width=28,
        height=28,
        fg_color=Theme.ACCENT_DARK,
        corner_radius=14,
        font=ctk.CTkFont(size=12, weight="bold"),
        text_color=Theme.TEXT,
    )
    badge.pack(side="left")
    ctk.CTkLabel(
        head,
        text=title,
        font=ctk.CTkFont(size=12, weight="bold"),
        text_color=Theme.TEXT,
        anchor="w",
    ).pack(side="left", padx=(10, 0))
    body = ctk.CTkFrame(frame, fg_color="transparent")
    body.pack(fill="x", padx=12, pady=(0, 12))
    body_builder(body)


def btn_primary(
    parent,
    text: str,
    command: Callable[[], None],
    *,
    width: int = 120,
    height: int = 30,
) -> ctk.CTkButton:
    return ctk.CTkButton(
        parent,
        text=text,
        width=width,
        height=height,
        fg_color=Theme.ACCENT_DARK,
        hover_color=Theme.ACCENT,
        text_color=Theme.TEXT,
        corner_radius=8,
        command=command,
    )


def btn_secondary(
    parent,
    text: str,
    command: Callable[[], None],
    *,
    width: int = 110,
    height: int = 30,
) -> ctk.CTkButton:
    return ctk.CTkButton(
        parent,
        text=text,
        width=width,
        height=height,
        fg_color=Theme.CARD_ALT,
        hover_color=Theme.BORDER,
        border_width=1,
        border_color=Theme.BORDER,
        text_color=Theme.TEXT,
        corner_radius=8,
        command=command,
    )


def btn_danger(
    parent,
    text: str,
    command: Callable[[], None],
    *,
    width: int = 90,
    height: int = 30,
) -> ctk.CTkButton:
    return ctk.CTkButton(
        parent,
        text=text,
        width=width,
        height=height,
        fg_color="#4a2230",
        hover_color="#5c2a3a",
        text_color=Theme.TEXT,
        corner_radius=8,
        command=command,
    )


def hint_label(parent, text: str, *, warn: bool = False) -> None:
    ctk.CTkLabel(
        parent,
        text=text,
        font=ctk.CTkFont(size=10),
        text_color=Theme.WARN if warn else Theme.DIM,
        anchor="w",
        justify="left",
        wraplength=520,
    ).pack(anchor="w", pady=(0, 4))


def panel(parent, **kwargs) -> ctk.CTkFrame:
    return ctk.CTkFrame(
        parent,
        fg_color=Theme.PANEL,
        corner_radius=10,
        border_width=1,
        border_color=Theme.BORDER,
        **kwargs,
    )


def status_pill(parent, key: str) -> ctk.CTkLabel:
    return ctk.CTkLabel(
        parent,
        text=f"{key}: …",
        font=ctk.CTkFont(size=10, weight="bold"),
        text_color=Theme.DIM,
        fg_color=Theme.CARD_ALT,
        corner_radius=8,
        padx=10,
        pady=4,
    )


def set_pill(label: ctk.CTkLabel, key: str, ok: bool, detail: str = "") -> None:
    mark = "●" if ok else "○"
    color = Theme.SUCCESS if ok else Theme.DIM
    suffix = f" {detail}" if detail else ""
    label.configure(text=f"{mark} {key}{suffix}", text_color=color)
