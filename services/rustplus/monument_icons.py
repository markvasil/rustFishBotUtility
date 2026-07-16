from __future__ import annotations

from contextlib import contextmanager
from typing import Dict, Iterator, Tuple

from PIL import Image

# Оригинальные PNG в rustplus — 200×200.
MONUMENT_ICON_SIZE = 72
# Видимый размер входа в метро (рисунок внутри холста).
METRO_ICON_SIZE = 52
# rustplus.paste + format_coord рассчитаны на ~150px (сдвиг -75).
_RUSTPLUS_ICON_CANVAS = 150

_METRO_TOKENS = frozenset({
    "train_tunnel_link_display_name",
    "train_tunnel_display_name",
})

# Имена токенов из rustplus.utils.utils.convert_monument
_KNOWN_MONUMENT_TOKENS = (
    "supermarket",
    "mining_outpost_display_name",
    "gas_station",
    "fishing_village_display_name",
    "large_fishing_village_display_name",
    "lighthouse_display_name",
    "excavator",
    "water_treatment_plant_display_name",
    "train_yard_display_name",
    "outpost",
    "bandit_camp",
    "jungle_ziggurat",
    "junkyard_display_name",
    "dome_monument_name",
    "satellite_dish_display_name",
    "power_plant_display_name",
    "military_tunnels_display_name",
    "airfield_display_name",
    "launchsite",
    "sewer_display_name",
    "oil_rig_small",
    "large_oil_rig",
    "underwater_lab",
    "AbandonedMilitaryBase",
    "ferryterminal",
    "harbor_display_name",
    "harbor_2_display_name",
    "arctic_base_a",
    "arctic_base_b",
    "missile_silo_monument",
    "stables_a",
    "stables_b",
    "mining_quarry_stone_display_name",
    "mining_quarry_sulfur_display_name",
    "mining_quarry_hqm_display_name",
    "train_tunnel_link_display_name",
    "train_tunnel_display_name",
    "radtown",
)


class _SkipForcedResize(dict):
    """
    rustplus.get_map делает icon.resize((150, 150)), если token in override_images.
    __contains__ = False отключает этот ресайз, но __getitem__ всё ещё отдаёт наши иконки.
    """

    def __contains__(self, key: object) -> bool:
        return False


def _pad_centered(icon: Image.Image, canvas_size: int) -> Image.Image:
    """Кладёт мелкую иконку в центр прозрачного холста под format_coord rustplus."""
    if icon.mode != "RGBA":
        icon = icon.convert("RGBA")
    canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    x = (canvas_size - icon.width) // 2
    y = (canvas_size - icon.height) // 2
    canvas.paste(icon, (x, y), icon)
    return canvas


def build_small_monument_overrides(icon_size: int = MONUMENT_ICON_SIZE) -> Dict[str, Image.Image]:
    """Готовит уменьшенные иконки для get_map(..., override_images=...)."""
    try:
        from rustplus.utils.utils import convert_monument
    except Exception:
        return {}

    size = max(24, int(icon_size))
    metro = max(20, int(METRO_ICON_SIZE))
    overrides: Dict[str, Image.Image] = _SkipForcedResize()
    for token in _KNOWN_MONUMENT_TOKENS:
        try:
            icon = convert_monument(token, {})
        except Exception:
            continue
        if token in _METRO_TOKENS:
            # Мелкий рисунок, но холст 150×150 — иначе format_coord(-75) уносит точку.
            icon = icon.resize((metro, metro), Image.Resampling.LANCZOS)
            icon = _pad_centered(icon, _RUSTPLUS_ICON_CANVAS)
        else:
            icon = icon.resize((size, size), Image.Resampling.LANCZOS)
            if icon.mode != "RGBA":
                icon = icon.convert("RGBA")
        overrides[token] = icon
    return overrides


@contextmanager
def patch_rustplus_metro_resize() -> Iterator[None]:
    """
    rustplus жёстко делает train_tunnel_display_name.resize((100, 125)).
    Не даём сплющить наш 150×150 холст с мелкой иконкой по центру.
    """
    original = Image.Image.resize

    def _resize(self, size, resample=None, *args, **kwargs):  # noqa: ANN001
        want: Tuple[int, ...] = tuple(size)
        if want == (100, 125) and self.size == (_RUSTPLUS_ICON_CANVAS, _RUSTPLUS_ICON_CANVAS):
            return self.copy()
        if resample is None:
            return original(self, size, *args, **kwargs)
        return original(self, size, resample, *args, **kwargs)

    Image.Image.resize = _resize  # type: ignore[method-assign]
    try:
        yield
    finally:
        Image.Image.resize = original  # type: ignore[method-assign]
