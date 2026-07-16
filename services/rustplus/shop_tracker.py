from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from services.rustplus.live_format import resolve_item_name


class ShopTracker:
    """Алерты магазинов и простая аналитика сделок."""

    def __init__(self) -> None:
        self._seen_ids: Set[int] = set()
        self._stock_state: Dict[int, bool] = {}
        self._offer_stock_state: Dict[tuple[int, int, int, int, int], int] = {}
        self._primed = False

    def reset(self) -> None:
        self._seen_ids.clear()
        self._stock_state.clear()
        self._offer_stock_state.clear()
        self._primed = False

    def detect_changes(
        self,
        vendors: List[Dict[str, Any]],
        *,
        alerts_enabled: bool = True,
        watched_item_ids: Optional[Set[int]] = None,
        item_name_fn: Optional[Callable[[int], str]] = None,
    ) -> List[Dict[str, str]]:
        if not alerts_enabled:
            self._prime(vendors)
            return []

        watched_item_ids = watched_item_ids or set()
        alerts: List[Dict[str, str]] = []
        current_ids = {int(v["id"]) for v in vendors if v.get("id") is not None}

        if not self._primed:
            self._prime(vendors)
            return alerts

        for vendor in vendors:
            vid = vendor.get("id")
            if vid is None:
                continue
            vid = int(vid)
            if vid not in self._seen_ids:
                alerts.append(
                    {
                        "title": "Новый магазин",
                        "message": f"🛒 {vendor.get('name', 'Магазин')} [{vendor.get('grid', '?')}]",
                    }
                )

            out = bool(vendor.get("out_of_stock"))
            prev = self._stock_state.get(vid)
            if prev is False and out:
                alerts.append(
                    {
                        "title": "Магазин пуст",
                        "message": f"📭 {vendor.get('name', 'Магазин')} [{vendor.get('grid', '?')}]",
                    }
                )
            if prev is True and not out:
                alerts.append(
                    {
                        "title": "Товар в наличии",
                        "message": f"✅ {vendor.get('name', 'Магазин')} снова в наличии [{vendor.get('grid', '?')}]",
                    }
                )
            self._stock_state[vid] = out

            for order in vendor.get("sell_orders", []):
                item_id = int(order.get("item_id", 0))
                stock = int(order.get("amount_in_stock", 0))
                offer_key = (
                    vid,
                    item_id,
                    int(order.get("currency_id", 0)),
                    int(order.get("cost_per_item", 0)),
                    int(order.get("quantity", 0)),
                )
                prev_stock = self._offer_stock_state.get(offer_key)
                if item_id in watched_item_ids and stock > 0 and (prev_stock is None or prev_stock <= 0):
                    item_name = item_name_fn(item_id) if item_name_fn else str(item_id)
                    alerts.append(
                        {
                            "title": "Watchlist",
                            "message": (
                                f"⭐ {item_name} доступен: "
                                f"{vendor.get('name', 'Магазин')} [{vendor.get('grid', '?')}]"
                            ),
                        }
                    )
                self._offer_stock_state[offer_key] = stock

        for lost_id in self._seen_ids - current_ids:
            alerts.append({"title": "Магазин пропал", "message": f"❌ Магазин #{lost_id} исчез с карты"})

        self._seen_ids = current_ids
        return alerts

    def _prime(self, vendors: List[Dict[str, Any]]) -> None:
        self._seen_ids = {int(v["id"]) for v in vendors if v.get("id") is not None}
        self._stock_state = {
            int(v["id"]): bool(v.get("out_of_stock"))
            for v in vendors
            if v.get("id") is not None
        }
        self._offer_stock_state = {}
        for vendor in vendors:
            vid = vendor.get("id")
            if vid is None:
                continue
            vid = int(vid)
            for order in vendor.get("sell_orders", []):
                offer_key = (
                    vid,
                    int(order.get("item_id", 0)),
                    int(order.get("currency_id", 0)),
                    int(order.get("cost_per_item", 0)),
                    int(order.get("quantity", 0)),
                )
                self._offer_stock_state[offer_key] = int(order.get("amount_in_stock", 0))
        self._primed = True

    def profit_trades(self, vendors: List[Dict[str, Any]], item_id: int) -> List[Dict[str, Any]]:
        start_item = int(item_id)
        edges: Dict[int, List[Dict[str, Any]]] = {}

        for vendor in vendors:
            for order in vendor.get("sell_orders", []):
                source = int(order.get("currency_id", 0))
                target = int(order.get("item_id", 0))
                cost = int(order.get("cost_per_item", 0))
                qty = int(order.get("quantity", 0))
                stock = int(order.get("amount_in_stock", 0))
                if source == 0 or target == 0 or cost <= 0 or qty <= 0 or stock <= 0:
                    continue
                edge = {
                    "source": source,
                    "target": target,
                    "cost": cost,
                    "qty": qty,
                    "rate": qty / cost,
                    "vendor": vendor,
                    "order": order,
                }
                edges.setdefault(source, []).append(edge)

        results: List[Dict[str, Any]] = []
        seen_routes: Set[Tuple[int, ...]] = set()

        def route_text(path: List[Dict[str, Any]]) -> str:
            segments: List[str] = []
            for edge in path:
                vendor = edge["vendor"]
                segments.append(
                    f"{resolve_item_name(edge['source'])} -> {resolve_item_name(edge['target'])} "
                    f"[{vendor.get('grid', '?')}]"
                )
            return " | ".join(segments)

        def dfs(current_item: int, amount: float, path: List[Dict[str, Any]], visited: Set[int], depth: int) -> None:
            if depth == 0:
                return
            for edge in edges.get(current_item, []):
                nxt = int(edge["target"])
                new_amount = amount * float(edge["rate"])
                new_path = path + [edge]
                if nxt == start_item and len(new_path) >= 2 and new_amount > 1.0:
                    signature = tuple(int(step["vendor"].get("id", 0)) for step in new_path)
                    if signature in seen_routes:
                        continue
                    seen_routes.add(signature)
                    results.append(
                        {
                            "item_id": start_item,
                            "profit": round(new_amount - 1.0, 3),
                            "profit_percent": round((new_amount - 1.0) * 100.0, 1),
                            "final_amount": round(new_amount, 3),
                            "hops": len(new_path),
                            "path": new_path,
                            "buy": {
                                "vendor": new_path[0]["vendor"].get("name"),
                                "grid": new_path[0]["vendor"].get("grid", "?"),
                                "order": new_path[0]["order"],
                            },
                            "sell": {
                                "vendor": new_path[-1]["vendor"].get("name"),
                                "grid": new_path[-1]["vendor"].get("grid", "?"),
                                "order": new_path[-1]["order"],
                            },
                            "route": route_text(new_path),
                        }
                    )
                    continue
                if nxt in visited:
                    continue
                dfs(nxt, new_amount, new_path, visited | {nxt}, depth - 1)

        dfs(start_item, 1.0, [], {start_item}, 3)
        results.sort(key=lambda entry: (-float(entry["profit"]), int(entry["hops"])))
        return results[:10]
