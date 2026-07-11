from __future__ import annotations

from typing import Any, Dict, List, Optional

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
        "x": marker.x,
        "y": marker.y,
        "grid": world_to_grid(marker.x, marker.y, map_size or 0),
        "out_of_stock": marker.out_of_stock,
        "sell_orders": orders,
    }


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

    results: List[Dict[str, Any]] = []
    for vendor in vendors:
        name = str(vendor.get("name", "")).lower()
        if q in name:
            results.append(vendor)
            continue
        for order in vendor.get("sell_orders", []):
            item_id = str(order.get("item_id", ""))
            if q in item_id:
                results.append(vendor)
                break
    return results
