from __future__ import annotations

import hashlib
from typing import Any, Callable, Dict, List, Optional

from rustplus.structs.rust_marker import RustMarker
from rustplus.structs.rust_team_info import RustTeamInfo
from rustplus.utils.utils import convert_coordinates

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


def world_to_grid(x: float, y: float, map_size: int) -> str:
    if not map_size:
        return "?"
    try:
        col, row = convert_coordinates((int(x), int(y)), map_size)
        return f"{col}{row}"
    except Exception:
        return "?"


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
        "grid": world_to_grid(marker.x, marker.y, map_size or 0),
        "out_of_stock": marker.out_of_stock,
        "sell_orders": orders,
    }


def classify_vendor(vendor: Dict[str, Any]) -> str:
    if vendor.get("type") == RustMarker.TravelingVendor:
        return "traveling"
    steam_id = int(vendor.get("steam_id") or 0)
    if steam_id > 0:
        return "player"
    return "monument"


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


def vendors_state_signature(vendors: List[Dict[str, Any]]) -> str:
    """Полная подпись всех лавок: состав лотов, цены, остатки, наличие."""
    lines: List[str] = []
    for vendor in sorted(vendors, key=lambda entry: int(entry.get("id") or 0)):
        lines.append(
            "v|{id}|{name}|{grid}|{out}|{steam}|{type}|{x}|{y}".format(
                id=int(vendor.get("id") or 0),
                name=str(vendor.get("name", "")),
                grid=str(vendor.get("grid", "")),
                out=int(bool(vendor.get("out_of_stock"))),
                steam=int(vendor.get("steam_id") or 0),
                type=int(vendor.get("type") or 0),
                x=vendor.get("x"),
                y=vendor.get("y"),
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


def format_markers(markers: List[RustMarker], map_size: Optional[int] = None) -> Dict[str, Any]:
    events: List[Dict[str, Any]] = []
    vendors: List[Dict[str, Any]] = []
    formatted = [format_marker(marker, map_size) for marker in markers]
    for item in formatted:
        if item["type"] in EVENT_MARKER_TYPES:
            events.append(item)
        if item["type"] in VENDOR_MARKER_TYPES:
            vendors.append(item)
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
