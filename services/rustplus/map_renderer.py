from __future__ import annotations

import math
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from services.rustplus.live_format import world_to_map_pixel, upkeep_hours_left


def upkeep_color(hours: Optional[float]) -> Tuple[int, int, int, int]:
    if hours is None:
        return (148, 163, 184, 255)
    if hours < 1:
        return (248, 113, 113, 255)
    if hours < 6:
        return (251, 191, 36, 255)
    return (74, 222, 128, 255)


def cluster_vendors(
    vendors: List[Dict[str, Any]],
    map_size: int,
    image_width: int,
    image_height: int,
    radius_px: int = 28,
) -> List[Dict[str, Any]]:
    if not vendors:
        return []

    points: List[Dict[str, Any]] = []
    for vendor in vendors:
        x = vendor.get("x")
        y = vendor.get("y")
        if x is None or y is None:
            continue
        px, py = world_to_map_pixel(float(x), float(y), map_size, image_width, image_height)
        points.append({**vendor, "px": px, "py": py})

    clusters: List[Dict[str, Any]] = []
    used = [False] * len(points)
    for i, point in enumerate(points):
        if used[i]:
            continue
        group = [point]
        used[i] = True
        for j in range(i + 1, len(points)):
            if used[j]:
                continue
            other = points[j]
            dist = math.hypot(point["px"] - other["px"], point["py"] - other["py"])
            if dist <= radius_px:
                group.append(other)
                used[j] = True
        cx = sum(item["px"] for item in group) // len(group)
        cy = sum(item["py"] for item in group) // len(group)
        clusters.append(
            {
                "px": cx,
                "py": cy,
                "count": len(group),
                "vendors": group,
                "name": group[0].get("name", "Магазин"),
            }
        )
    return clusters


class MapRenderer:
    """Общая отрисовка оверлеев поверх карты."""

    def __init__(self) -> None:
        self._avatar_cache: Dict[int, Image.Image] = {}
        self._base_cache: Dict[str, Tuple[float, Image.Image]] = {}
        self._avatar_lock = threading.Lock()

    def set_avatar(self, steam_id: int, image: Image.Image) -> None:
        with self._avatar_lock:
            self._avatar_cache[int(steam_id)] = image

    def invalidate_base(self, base_path: Optional[str] = None) -> None:
        if base_path is None:
            self._base_cache.clear()
            return
        self._base_cache.pop(str(base_path), None)

    def get_base_size(self, base_path: str) -> Tuple[int, int]:
        image = self._load_base(base_path)
        return image.size

    def _load_base(self, base_path: str) -> Image.Image:
        path = Path(base_path)
        mtime = path.stat().st_mtime if path.exists() else 0.0
        cached = self._base_cache.get(str(base_path))
        if cached and cached[0] == mtime:
            return cached[1].copy()
        image = Image.open(base_path)
        if image.mode != "RGBA":
            image = image.convert("RGBA")
        self._base_cache[str(base_path)] = (mtime, image.copy())
        return image

    def render(
        self,
        base_path: str,
        *,
        map_size: Optional[int],
        team_members: Optional[List[Dict[str, Any]]] = None,
        death_markers: Optional[List[Dict[str, Any]]] = None,
        drawings: Optional[List[Dict[str, Any]]] = None,
        events: Optional[List[Dict[str, Any]]] = None,
        vendors: Optional[List[Dict[str, Any]]] = None,
        tracked_event_id: Optional[int] = None,
        follow_steam_id: Optional[int] = None,
        view_center: Optional[Tuple[float, float]] = None,
        zoom: float = 1.0,
        output_size: Optional[Tuple[int, int]] = None,
        show_avatars: bool = True,
        cluster_shops: bool = True,
    ) -> Image.Image:
        image = self._load_base(base_path)
        width, height = image.size
        if map_size and team_members:
            self._draw_team(image, team_members, map_size, show_avatars)
        if map_size and death_markers:
            self._draw_deaths(image, death_markers, map_size)
        if map_size and drawings:
            self._draw_drawings(image, drawings, map_size)
        if map_size and events:
            self._draw_events(image, events, map_size, tracked_event_id)
        if map_size and vendors:
            if cluster_shops:
                clusters = cluster_vendors(vendors, map_size, width, height)
                self._draw_shop_clusters(image, clusters)
            else:
                self._draw_vendors(image, vendors, map_size)

        if view_center and zoom != 1.0:
            image = self._crop_zoom(image, view_center, zoom, output_size)
        elif output_size:
            image = image.resize(output_size, Image.Resampling.LANCZOS)

        if follow_steam_id and map_size and team_members:
            image = self._apply_follow_crop(
                image, team_members, follow_steam_id, map_size, output_size, zoom,
            )

        return image.convert("RGB")

    def _draw_team(
        self,
        image: Image.Image,
        members: List[Dict[str, Any]],
        map_size: int,
        show_avatars: bool,
    ) -> None:
        draw = ImageDraw.Draw(image)
        w, h = image.size
        radius = max(6, min(w, h) // 40)
        font = self._font()

        for member in members:
            x, y = member.get("x"), member.get("y")
            if x is None or y is None:
                continue
            px, py = world_to_map_pixel(float(x), float(y), map_size, w, h)
            steam_id = int(member.get("steam_id", 0))
            avatar = None
            if show_avatars:
                with self._avatar_lock:
                    avatar = self._avatar_cache.get(steam_id)

            if avatar:
                size = radius * 2
                av = avatar.resize((size, size), Image.Resampling.LANCZOS)
                mask = Image.new("L", (size, size), 0)
                ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
                image.paste(av, (px - radius, py - radius), mask)
                outline = (74, 222, 128, 255) if member.get("is_online") else (148, 163, 184, 255)
                draw.ellipse(
                    (px - radius, py - radius, px + radius, py + radius),
                    outline=outline,
                    width=2,
                )
            else:
                if not member.get("is_alive", True):
                    fill = (248, 113, 113, 255)
                elif member.get("is_online"):
                    fill = (74, 222, 128, 255)
                else:
                    fill = (148, 163, 184, 255)
                draw.ellipse(
                    (px - radius, py - radius, px + radius, py + radius),
                    fill=fill,
                    outline=(255, 255, 255, 220),
                    width=2,
                )
                name = str(member.get("name", "?"))[:1].upper()
                if font and name:
                    tw, th = draw.textbbox((0, 0), name, font=font)[2:]
                    draw.text((px - tw // 2, py - th // 2 - 1), name, fill=(15, 17, 23, 255), font=font)

    def _draw_deaths(
        self,
        image: Image.Image,
        markers: List[Dict[str, Any]],
        map_size: int,
    ) -> None:
        draw = ImageDraw.Draw(image)
        w, h = image.size
        for marker in markers:
            x, y = marker.get("x"), marker.get("y")
            if x is None or y is None:
                continue
            px, py = world_to_map_pixel(float(x), float(y), map_size, w, h)
            r = max(8, min(w, h) // 35)
            draw.line((px - r, py - r, px + r, py + r), fill=(248, 113, 113, 255), width=3)
            draw.line((px - r, py + r, px + r, py - r), fill=(248, 113, 113, 255), width=3)
            draw.ellipse(
                (px - r, py - r, px + r, py + r),
                outline=(255, 255, 255, 200),
                width=2,
            )

    def _draw_drawings(
        self,
        image: Image.Image,
        drawings: List[Dict[str, Any]],
        map_size: int,
    ) -> None:
        draw = ImageDraw.Draw(image)
        w, h = image.size
        font = self._font()
        for item in drawings:
            x, y = item.get("x"), item.get("y")
            if x is None or y is None:
                continue
            px, py = world_to_map_pixel(float(x), float(y), map_size, w, h)
            color = self._parse_color(item.get("color", "#fbbf24"))
            r = 6
            draw.ellipse((px - r, py - r, px + r, py + r), fill=color)
            text = str(item.get("text", ""))[:24]
            if text and font:
                draw.text((px + 8, py - 6), text, fill=color, font=font)

    def _draw_events(
        self,
        image: Image.Image,
        events: List[Dict[str, Any]],
        map_size: int,
        tracked_id: Optional[int],
    ) -> None:
        draw = ImageDraw.Draw(image)
        w, h = image.size
        for event in events:
            x, y = event.get("x"), event.get("y")
            if x is None or y is None:
                continue
            px, py = world_to_map_pixel(float(x), float(y), map_size, w, h)
            is_tracked = tracked_id is not None and event.get("id") == tracked_id
            color = (96, 165, 250, 255) if is_tracked else (110, 231, 255, 200)
            r = 10 if is_tracked else 7
            draw.ellipse((px - r, py - r, px + r, py + r), fill=color, outline=(255, 255, 255, 220), width=2)

    def _draw_vendors(self, image: Image.Image, vendors: List[Dict[str, Any]], map_size: int) -> None:
        draw = ImageDraw.Draw(image)
        w, h = image.size
        for vendor in vendors:
            x, y = vendor.get("x"), vendor.get("y")
            if x is None or y is None:
                continue
            px, py = world_to_map_pixel(float(x), float(y), map_size, w, h)
            draw.rectangle((px - 5, py - 5, px + 5, py + 5), fill=(192, 132, 252, 220))

    def _draw_shop_clusters(self, image: Image.Image, clusters: List[Dict[str, Any]]) -> None:
        draw = ImageDraw.Draw(image)
        font = self._font()
        for cluster in clusters:
            px, py = cluster["px"], cluster["py"]
            count = cluster["count"]
            r = 10 if count == 1 else 12
            draw.ellipse((px - r, py - r, px + r, py + r), fill=(192, 132, 252, 230), outline=(255, 255, 255, 220), width=2)
            if count > 1 and font:
                label = str(count)
                tw, th = draw.textbbox((0, 0), label, font=font)[2:]
                draw.text((px - tw // 2, py - th // 2), label, fill=(15, 17, 23, 255), font=font)

    def _apply_follow_crop(
        self,
        image: Image.Image,
        members: List[Dict[str, Any]],
        steam_id: int,
        map_size: int,
        output_size: Optional[Tuple[int, int]],
        zoom: float,
    ) -> Image.Image:
        target = None
        for member in members:
            if int(member.get("steam_id", 0)) == int(steam_id):
                target = member
                break
        if not target:
            return image

        w, h = image.size
        px, py = world_to_map_pixel(float(target["x"]), float(target["y"]), map_size, w, h)
        crop_w = int(w / max(zoom, 1.0))
        crop_h = int(h / max(zoom, 1.0))
        left = max(0, min(px - crop_w // 2, w - crop_w))
        top = max(0, min(py - crop_h // 2, h - crop_h))
        cropped = image.crop((left, top, left + crop_w, top + crop_h))
        if output_size:
            return cropped.resize(output_size, Image.Resampling.LANCZOS)
        return cropped

    @staticmethod
    def _crop_zoom(
        image: Image.Image,
        center: Tuple[float, float],
        zoom: float,
        output_size: Optional[Tuple[int, int]],
    ) -> Image.Image:
        w, h = image.size
        cx, cy = center
        crop_w = int(w / max(zoom, 1.0))
        crop_h = int(h / max(zoom, 1.0))
        left = max(0, min(int(cx - crop_w / 2), w - crop_w))
        top = max(0, min(int(cy - crop_h / 2), h - crop_h))
        cropped = image.crop((left, top, left + crop_w, top + crop_h))
        if output_size:
            return cropped.resize(output_size, Image.Resampling.LANCZOS)
        return cropped

    @staticmethod
    def _font():
        try:
            return ImageFont.load_default()
        except Exception:
            return None

    @staticmethod
    def _parse_color(value: str) -> Tuple[int, int, int, int]:
        value = str(value).lstrip("#")
        if len(value) == 6:
            r, g, b = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
            return r, g, b, 255
        return 251, 191, 36, 255
