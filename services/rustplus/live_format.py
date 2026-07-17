from __future__ import annotations

import hashlib
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from rustplus.structs.rust_marker import RustMarker
from rustplus.structs.rust_team_info import RustTeamInfo

from services.rustplus.grid_coords import world_to_grid

# Монументы с NPC-лавками (safe zone). steam_id у маркеров больше не приходит.
SAFE_ZONE_MONUMENT_TOKENS = frozenset({
    "outpost",
    "bandit_camp",
    "fishing_village_display_name",
    "large_fishing_village_display_name",
    "stables_a",
    "stables_b",
})
# На практике NPC ≤ ~50 от центра; 100 — запас для крупного Outpost.
SAFE_ZONE_VENDOR_RADIUS = 100.0

# Fallback, если карта с монументами ещё не загружена.
_NPC_VENDOR_NAMES = frozenset({
    "building",
    "vendor farming",
    "vehicles",
    "boat vendor",
    "weapons",
    "exchange",
    "shop keeper",
    "fish exchange",
    "components",
    "stables shopkeeper",
    "resources",
    "tools & stuff",
    "food",
    "resource exchange",
    "output outfitters",
})

MARKER_TYPE_NAMES = {
    RustMarker.PlayerMarker: "Игрок",
    RustMarker.ExplosionMarker: "Взрыв",
    RustMarker.VendingMachineMarker: "Магазин",
    RustMarker.ChinookMarker: "Chinook",
    RustMarker.CargoShipMarker: "Карго",
    RustMarker.CrateMarker: "Ящик",
    RustMarker.RadiusMarker: "Зона",
    RustMarker.PatrolHelicopterMarker: "Патрульный верт",
    RustMarker.TravelingVendor: "Бродячий торговец",
}

EVENT_MARKER_TYPES = {
    RustMarker.ChinookMarker,
    RustMarker.CargoShipMarker,
    RustMarker.PatrolHelicopterMarker,
    RustMarker.CrateMarker,
}

VENDOR_MARKER_TYPES = {
    RustMarker.VendingMachineMarker,
    RustMarker.TravelingVendor,
}


def _clamp_map(value: float, map_size: Optional[int]) -> float:
    if not map_size:
        return value
    return max(0.0, min(float(map_size), value))


def _smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def has_active_motion(
    item: Dict[str, Any],
    *,
    now_ts: Optional[float] = None,
    horizon_sec: float = 12.0,
) -> bool:
    """Есть ли ещё анимация/экстраполяция у маркера (для тиков карты)."""
    try:
        now_ts = float(now_ts or time.time())
        sample_ts = float(item.get("_sample_ts") or now_ts)
        age = max(0.0, now_ts - sample_ts)
        interp = float(item.get("_interp_sec") or 0.0)
        from_x = item.get("_from_x")
        from_y = item.get("_from_y")
        to_x = item.get("_to_x", item.get("x"))
        to_y = item.get("_to_y", item.get("y"))
        if (
            from_x is not None
            and from_y is not None
            and to_x is not None
            and to_y is not None
            and (
                abs(float(from_x) - float(to_x)) >= 0.5
                or abs(float(from_y) - float(to_y)) >= 0.5
            )
            and age < interp + 0.05
        ):
            return True
        vx = abs(float(item.get("_vx") or 0.0))
        vy = abs(float(item.get("_vy") or 0.0))
        if (vx > 0.05 or vy > 0.05) and age < interp + horizon_sec:
            return True
        return False
    except (TypeError, ValueError):
        return False


def add_motion_vectors(
    current_items: List[Dict[str, Any]],
    previous_items: List[Dict[str, Any]],
    *,
    key_name: str,
    sample_ts: Optional[float] = None,
    map_size: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Добавляет скорость и сегмент интерполяции, чтобы иконки не телепортировались."""
    sample_ts = float(sample_ts or time.time())
    prev_by_key: Dict[Any, Dict[str, Any]] = {}
    for item in previous_items:
        key = item.get(key_name)
        if key is not None:
            prev_by_key[key] = item

    enriched: List[Dict[str, Any]] = []
    for item in current_items:
        row = dict(item)
        key = row.get(key_name)
        prev = prev_by_key.get(key)
        vx = 0.0
        vy = 0.0
        if row.get("x") is None or row.get("y") is None:
            enriched.append(row)
            continue
        try:
            to_x = float(row["x"])
            to_y = float(row["y"])
        except (TypeError, ValueError, KeyError):
            enriched.append(row)
            continue

        from_x = to_x
        from_y = to_y
        interp_sec = 1.0
        if prev is not None and prev.get("x") is not None and prev.get("y") is not None:
            prev_ts = float(prev.get("_sample_ts") or sample_ts)
            dt = max(0.001, sample_ts - prev_ts)
            try:
                prev_x = float(prev.get("x") or 0.0)
                prev_y = float(prev.get("y") or 0.0)
                vx = (to_x - prev_x) / dt
                vy = (to_y - prev_y) / dt
            except (TypeError, ValueError):
                vx = 0.0
                vy = 0.0
            # Старт сегмента = где иконка уже нарисована (без скачка).
            visual = project_motion([prev], now_ts=sample_ts, map_size=map_size)[0]
            try:
                from_x = float(visual.get("x") if visual.get("x") is not None else to_x)
                from_y = float(visual.get("y") if visual.get("y") is not None else to_y)
            except (TypeError, ValueError):
                from_x, from_y = to_x, to_y
            # Двигаемся к новой точке за типичный интервал между сэмплами.
            interp_sec = min(20.0, max(0.75, dt))

        row["_sample_ts"] = sample_ts
        row["_vx"] = vx
        row["_vy"] = vy
        row["_from_x"] = from_x
        row["_from_y"] = from_y
        row["_to_x"] = to_x
        row["_to_y"] = to_y
        row["_interp_sec"] = interp_sec
        enriched.append(row)
    return enriched


def project_motion(
    items: List[Dict[str, Any]],
    *,
    now_ts: Optional[float] = None,
    horizon_sec: float = 12.0,
    map_size: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Плавная позиция: lerp from→to между poll'ами, затем короткая экстраполяция."""
    now_ts = float(now_ts or time.time())
    projected: List[Dict[str, Any]] = []
    for item in items:
        row = dict(item)
        x = row.get("x")
        y = row.get("y")
        if x is None or y is None:
            projected.append(row)
            continue
        try:
            sample_ts = float(row.get("_sample_ts") or now_ts)
            age = max(0.0, now_ts - sample_ts)
            vx = float(row.get("_vx") or 0.0)
            vy = float(row.get("_vy") or 0.0)
            to_x = float(row["_to_x"]) if row.get("_to_x") is not None else float(x)
            to_y = float(row["_to_y"]) if row.get("_to_y") is not None else float(y)
            from_x = float(row["_from_x"]) if row.get("_from_x") is not None else to_x
            from_y = float(row["_from_y"]) if row.get("_from_y") is not None else to_y
            interp_sec = float(row.get("_interp_sec") or 0.0)

            if interp_sec > 0.0 and (from_x != to_x or from_y != to_y):
                if age < interp_sec:
                    t = _smoothstep(age / interp_sec)
                    px = from_x + (to_x - from_x) * t
                    py = from_y + (to_y - from_y) * t
                else:
                    overshoot = min(horizon_sec, age - interp_sec)
                    px = to_x + vx * overshoot
                    py = to_y + vy * overshoot
            else:
                # Старый формат / нет сегмента: dead reckoning от серверной точки.
                extrap_age = min(horizon_sec, age)
                px = float(x) + vx * extrap_age
                py = float(y) + vy * extrap_age

            px = _clamp_map(px, map_size)
            py = _clamp_map(py, map_size)
            row["x"] = px
            row["y"] = py
            row["grid"] = world_to_grid(px, py, int(map_size or 0))
        except (TypeError, ValueError):
            pass
        projected.append(row)
    return projected


def world_to_map_pixel(
    x: float, y: float, map_size: int, image_width: int, image_height: int,
) -> tuple[int, int]:
    if not map_size or image_width <= 0 or image_height <= 0:
        return 0, 0
    px = int(float(x) / map_size * image_width)
    py = int((map_size - float(y)) / map_size * image_height)
    px = max(0, min(px, image_width - 1))
    py = max(0, min(py, image_height - 1))
    return px, py


def format_team(team: RustTeamInfo, map_size: Optional[int] = None) -> Dict[str, Any]:
    members: List[Dict[str, Any]] = []
    for member in team.members:
        members.append(
            {
                "name": member.name,
                "steam_id": member.steam_id,
                "is_online": member.is_online,
                "is_alive": member.is_alive,
                "x": member.x,
                "y": member.y,
                "grid": world_to_grid(member.x, member.y, map_size or 0),
            }
        )
    return {
        "leader_steam_id": team.leader_steam_id,
        "members": members,
    }


def format_marker(marker: RustMarker, map_size: Optional[int] = None) -> Dict[str, Any]:
    orders = []
    for order in marker.sell_orders:
        orders.append(
            {
                "item_id": order.item_id,
                "quantity": order.quantity,
                "currency_id": order.currency_id,
                "cost_per_item": order.cost_per_item,
                "amount_in_stock": order.amount_in_stock,
            }
        )
    return {
        "id": marker.id,
        "type": marker.type,
        "type_name": MARKER_TYPE_NAMES.get(marker.type, f"#{marker.type}"),
        "name": marker.name,
        "steam_id": marker.steam_id,
        "x": marker.x,
        "y": marker.y,
        "rotation": float(getattr(marker, "rotation", 0) or 0),
        "grid": world_to_grid(marker.x, marker.y, map_size or 0),
        "out_of_stock": marker.out_of_stock,
        "sell_orders": orders,
    }


def _monument_xy(monument: Any) -> Optional[Tuple[float, float]]:
    if isinstance(monument, dict):
        x, y = monument.get("x"), monument.get("y")
    else:
        x, y = getattr(monument, "x", None), getattr(monument, "y", None)
    if x is None or y is None:
        return None
    return float(x), float(y)


def _monument_token(monument: Any) -> str:
    if isinstance(monument, dict):
        return str(monument.get("token") or "")
    return str(getattr(monument, "token", "") or "")


def format_monuments(monuments: Optional[Sequence[Any]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for monument in monuments or []:
        xy = _monument_xy(monument)
        token = _monument_token(monument)
        if not xy or not token:
            continue
        result.append({"token": token, "x": xy[0], "y": xy[1]})
    return result


def is_near_safe_zone(
    x: float,
    y: float,
    monuments: Optional[Sequence[Any]] = None,
    *,
    radius: float = SAFE_ZONE_VENDOR_RADIUS,
) -> bool:
    if not monuments:
        return False
    radius_sq = float(radius) * float(radius)
    for monument in monuments:
        token = _monument_token(monument)
        if token not in SAFE_ZONE_MONUMENT_TOKENS:
            continue
        xy = _monument_xy(monument)
        if not xy:
            continue
        dx = float(x) - xy[0]
        dy = float(y) - xy[1]
        if dx * dx + dy * dy <= radius_sq:
            return True
    return False


def _looks_like_npc_vendor_name(name: str) -> bool:
    normalized = (name or "").strip().lower()
    if not normalized:
        return False
    if normalized in _NPC_VENDOR_NAMES:
        return True
    # Outpost: "Extra 1", "Extra 2", ...
    if normalized.startswith("extra ") and normalized[6:].isdigit():
        return True
    return False


def classify_vendor(
    vendor: Dict[str, Any],
    monuments: Optional[Sequence[Any]] = None,
) -> str:
    cached = vendor.get("kind")
    if cached in ("player", "monument", "traveling"):
        return str(cached)
    if vendor.get("type") == RustMarker.TravelingVendor:
        return "traveling"
    # Раньше Facepunch слал steam_id владельца; сейчас почти всегда 0.
    steam_id = int(vendor.get("steam_id") or 0)
    if steam_id > 0:
        return "player"
    x, y = vendor.get("x"), vendor.get("y")
    if (
        x is not None
        and y is not None
        and monuments
        and is_near_safe_zone(float(x), float(y), monuments)
    ):
        return "monument"
    if monuments:
        return "player"
    # Карта ещё не загружена — грубая эвристика по имени NPC.
    if _looks_like_npc_vendor_name(str(vendor.get("name") or "")):
        return "monument"
    return "player"


def annotate_vendor_kinds(
    vendors: List[Dict[str, Any]],
    monuments: Optional[Sequence[Any]] = None,
) -> List[Dict[str, Any]]:
    for vendor in vendors:
        vendor.pop("kind", None)
        vendor["kind"] = classify_vendor(vendor, monuments)
    return vendors


def vendor_primary_order(vendor: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    orders = vendor.get("sell_orders") or []
    if not orders:
        return None
    for order in orders:
        if int(order.get("amount_in_stock", 0)) > 0:
            return order
    return orders[0]


def resolve_item_name(item_id: int, item_name_fn: Optional[Callable[[int], str]] = None) -> str:
    if item_name_fn:
        return item_name_fn(int(item_id))
    try:
        from rustplus.utils.grab_items import translate_id_to_stack

        name = translate_id_to_stack(int(item_id))
        if name != "Not Found":
            return name
    except Exception:
        pass
    return "Неизвестный предмет"


def sort_vendors_for_display(
    vendors: List[Dict[str, Any]],
    *,
    sort_by: str = "name",
    item_name_fn: Optional[Callable[[int], str]] = None,
) -> List[Dict[str, Any]]:
    kind_order = {"player": 0, "traveling": 1, "monument": 2}
    sort_by = (sort_by or "name").lower()

    def name_key(vendor: Dict[str, Any]) -> tuple:
        return (
            kind_order.get(classify_vendor(vendor), 9),
            str(vendor.get("name", "")).lower(),
        )

    def item_key(vendor: Dict[str, Any]) -> tuple:
        order = vendor_primary_order(vendor)
        if not order:
            return ("\uffff", 0, str(vendor.get("name", "")).lower())
        item_name = resolve_item_name(order.get("item_id", 0), item_name_fn).lower()
        cost = int(order.get("cost_per_item", 0))
        return (item_name, cost, str(vendor.get("name", "")).lower())

    key = item_key if sort_by == "item" else name_key
    return sorted(vendors, key=key)


def profit_routes_signature(routes: Sequence[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for route in routes:
        lines.append(
            "p|{item}|{pct}|{amt}|{hops}|{text}".format(
                item=int(route.get("item_id") or 0),
                pct=float(route.get("profit_percent") or 0),
                amt=float(route.get("final_amount") or 0),
                hops=int(route.get("hops") or 0),
                text=str(route.get("route", "")),
            )
        )
    payload = "\n".join(lines)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest() if payload else "__empty__"


def vendor_catalog_ids_signature(items: Sequence[Dict[str, Any]]) -> str:
    """Подпись состава каталога: только какие item_id есть в наличии."""
    payload = ",".join(
        str(int(item.get("item_id", 0)))
        for item in sorted(items, key=lambda entry: int(entry.get("item_id", 0)))
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest() if payload else "__empty__"


def vendor_catalog_signature(items: Sequence[Dict[str, Any]]) -> str:
    """Подпись видимого каталога: только агрегаты, без остатков отдельных лавок."""
    lines: List[str] = []
    for item in sorted(items, key=lambda entry: int(entry.get("item_id", 0))):
        lines.append(
            "i|{id}|{name}|{shops}|{offers}|{cost}|{currency}".format(
                id=int(item.get("item_id", 0)),
                name=str(item.get("name", "")),
                shops=int(item.get("shop_count", 0)),
                offers=int(item.get("offer_count", 0)),
                cost=int(item.get("min_cost", 0)),
                currency=int(item.get("min_currency_id", 0)),
            )
        )
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def vendor_offers_signature(offers: Sequence[Dict[str, Any]]) -> str:
    """Подпись видимых предложений по выбранному товару."""
    lines: List[str] = []
    for offer in offers:
        vendor = offer.get("vendor") or {}
        order = offer.get("order") or {}
        lines.append(
            "o|{vid}|{grid}|{kind}|{cost}|{stock}|{item}|{currency}|{qty}".format(
                vid=int(vendor.get("id") or 0),
                grid=str(vendor.get("grid", "")),
                kind=str(vendor.get("kind") or classify_vendor(vendor)),
                cost=int(order.get("cost_per_item", 0)),
                stock=int(order.get("amount_in_stock", 0)),
                item=int(order.get("item_id", 0)),
                currency=int(order.get("currency_id", 0)),
                qty=int(order.get("quantity", 0)),
            )
        )
    payload = "\n".join(sorted(lines))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def vendors_state_signature(vendors: List[Dict[str, Any]]) -> str:
    """Полная подпись всех лавок: состав лотов, цены, остатки, наличие."""
    lines: List[str] = []
    for vendor in sorted(vendors, key=lambda entry: int(entry.get("id") or 0)):
        lines.append(
            "v|{id}|{name}|{grid}|{out}|{steam}|{type}|{kind}".format(
                id=int(vendor.get("id") or 0),
                name=str(vendor.get("name", "")),
                grid=str(vendor.get("grid", "")),
                out=int(bool(vendor.get("out_of_stock"))),
                steam=int(vendor.get("steam_id") or 0),
                type=int(vendor.get("type") or 0),
                kind=str(vendor.get("kind") or classify_vendor(vendor)),
            )
        )
        orders = vendor.get("sell_orders") or []
        for order in sorted(
            orders,
            key=lambda entry: (
                int(entry.get("item_id", 0)),
                int(entry.get("currency_id", 0)),
                int(entry.get("cost_per_item", 0)),
                int(entry.get("quantity", 0)),
            ),
        ):
            lines.append(
                "o|{vid}|{item}|{qty}|{currency}|{cost}|{stock}".format(
                    vid=int(vendor.get("id") or 0),
                    item=int(order.get("item_id", 0)),
                    qty=int(order.get("quantity", 0)),
                    currency=int(order.get("currency_id", 0)),
                    cost=int(order.get("cost_per_item", 0)),
                    stock=int(order.get("amount_in_stock", 0)),
                )
            )
    payload = "\n".join(lines)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_vendor_item_catalog(
    vendors: List[Dict[str, Any]],
    *,
    item_name_fn: Optional[Callable[[int], str]] = None,
    in_stock_only: bool = True,
) -> List[Dict[str, Any]]:
    catalog: Dict[int, Dict[str, Any]] = {}

    for vendor in vendors:
        vendor_id = vendor.get("id")
        for order in vendor.get("sell_orders", []):
            stock = int(order.get("amount_in_stock", 0))
            if in_stock_only and stock <= 0:
                continue
            item_id = int(order.get("item_id", 0))
            if not item_id:
                continue
            cost = int(order.get("cost_per_item", 0))
            entry = catalog.get(item_id)
            if entry is None:
                entry = {
                    "item_id": item_id,
                    "name": resolve_item_name(item_id, item_name_fn),
                    "shop_count": 0,
                    "offer_count": 0,
                    "min_cost": cost,
                    "min_currency_id": int(order.get("currency_id", 0)),
                    "_vendor_ids": set(),
                }
                catalog[item_id] = entry
            entry["offer_count"] += 1
            entry["_vendor_ids"].add(vendor_id)
            if cost < entry["min_cost"]:
                entry["min_cost"] = cost
                entry["min_currency_id"] = int(order.get("currency_id", 0))

    items = []
    for entry in catalog.values():
        entry["shop_count"] = len(entry.pop("_vendor_ids"))
        items.append(entry)
    return sorted(items, key=lambda item: str(item.get("name", "")).lower())


def filter_vendor_catalog_items(
    items: List[Dict[str, Any]],
    query: str,
) -> List[Dict[str, Any]]:
    q = query.strip().lower()
    if not q:
        return items
    return [item for item in items if q in str(item.get("name", "")).lower()]


def collect_item_offers(
    vendors: List[Dict[str, Any]],
    item_id: int,
    *,
    in_stock_only: bool = True,
) -> List[Dict[str, Any]]:
    item_id = int(item_id)
    offers: List[Dict[str, Any]] = []
    for vendor in vendors:
        for order in vendor.get("sell_orders", []):
            if int(order.get("item_id", 0)) != item_id:
                continue
            stock = int(order.get("amount_in_stock", 0))
            if in_stock_only and stock <= 0:
                continue
            offers.append({"vendor": vendor, "order": order})
    return sorted(
        offers,
        key=lambda offer: (
            int(offer["order"].get("cost_per_item", 0)),
            str(offer["vendor"].get("name", "")).lower(),
        ),
    )


def filter_vendors_by_kind(vendors: List[Dict[str, Any]], kind: str) -> List[Dict[str, Any]]:
    if not kind or kind == "all":
        return vendors
    return [vendor for vendor in vendors if classify_vendor(vendor) == kind]


def format_markers(
    markers: List[RustMarker],
    map_size: Optional[int] = None,
    monuments: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    events: List[Dict[str, Any]] = []
    vendors: List[Dict[str, Any]] = []
    formatted = [format_marker(marker, map_size) for marker in markers]
    for item in formatted:
        if item["type"] in EVENT_MARKER_TYPES:
            events.append(item)
        if item["type"] in VENDOR_MARKER_TYPES:
            vendors.append(item)
    annotate_vendor_kinds(vendors, monuments)
    return {"events": events, "vendors": vendors, "all": formatted}


def upkeep_hours_left(protection_expiry: int, server_time_raw: Optional[float]) -> Optional[float]:
    if not protection_expiry or server_time_raw is None:
        return None
    remaining = float(protection_expiry) - float(server_time_raw)
    return max(0.0, remaining / 3600.0)


def filter_vendors(vendors: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    q = query.strip().lower()
    if not q:
        return vendors

    try:
        from rustplus.utils.grab_items import translate_id_to_stack
    except Exception:
        translate_id_to_stack = None

    results: List[Dict[str, Any]] = []
    for vendor in vendors:
        name = str(vendor.get("name", "")).lower()
        if q in name:
            results.append(vendor)
            continue
        for order in vendor.get("sell_orders", []):
            item_id = str(order.get("item_id", ""))
            currency_id = str(order.get("currency_id", ""))
            if q in item_id or q in currency_id:
                results.append(vendor)
                break
            if translate_id_to_stack:
                item_name = str(translate_id_to_stack(order.get("item_id", 0))).lower()
                currency_name = str(translate_id_to_stack(order.get("currency_id", 0))).lower()
                if q in item_name or q in currency_name:
                    results.append(vendor)
                    break
    return results
