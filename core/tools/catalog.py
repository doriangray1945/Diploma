from typing import Any

from core.tools.base import BaseTool

# Imported lazily inside execute() to avoid cross-package import cycles
# (core/* should not statically depend on backend/app/*, and only execute()
# needs the resolvers).


# Field descriptions — MUST match dataset/generator.py:FIELD_DESCRIPTIONS so the
# model sees identical schema text at runtime as it did during training.
_FIELD_DESCRIPTIONS = {
    "category":    "Одна категория товара",
    "material":    "Материалы (массив, можно несколько)",
    "color":       "Цвета (массив, можно несколько)",
    "price_level": "Семантический ценовой сегмент",
    "min_price":   "Минимальная цена в рублях",
    "max_price":   "Максимальная цена в рублях",
    "search":      "Описательные слова: стиль (лофт, минимализм), персона (детский, офисный), эмоция (уютный), конкретные сорта (дуб, велюр)",
    "in_stock":    "Только товары в наличии",
}

# API-level enum (price segmentation contract — not catalog data)
_PRICE_LEVELS = ["budget", "mid", "premium"]


class ApplyFiltersTool(BaseTool):
    name = "apply_filters"
    # Description matches dataset/generator.py:TOOL_DESCRIPTIONS — keep short
    # to mirror training format exactly.
    description = "Применить фильтры к каталогу для поиска товаров"
    updates_context = {
        "last_search": "result",
        "visible_product_ids": "result.products[*].id",
        "current_filters": "result.filters",
    }

    # Static fallback (used if filter_options is empty — keeps schema valid).
    # Key order inside each field schema: type → enum → description (matches
    # dataset/generator.py:_tool_full_schema variant A).
    parameters = {
        "type": "object",
        "properties": {
            "category":    {"type": "string", "description": _FIELD_DESCRIPTIONS["category"]},
            "material":    {"type": "array", "items": {"type": "string"}, "description": _FIELD_DESCRIPTIONS["material"]},
            "color":       {"type": "array", "items": {"type": "string"}, "description": _FIELD_DESCRIPTIONS["color"]},
            "price_level": {"type": "string", "enum": _PRICE_LEVELS, "description": _FIELD_DESCRIPTIONS["price_level"]},
            "min_price":   {"type": "number", "description": _FIELD_DESCRIPTIONS["min_price"]},
            "max_price":   {"type": "number", "description": _FIELD_DESCRIPTIONS["max_price"]},
            "search":      {"type": "string", "description": _FIELD_DESCRIPTIONS["search"]},
            "in_stock":    {"type": "boolean", "description": _FIELD_DESCRIPTIONS["in_stock"]},
        },
    }

    def _build_parameters(self, filter_options: dict[str, Any]) -> dict[str, Any]:
        cats = list(filter_options.get("categories") or [])
        cols = list(filter_options.get("colors") or [])
        mats = list(filter_options.get("materials") or [])
        cat: dict[str, Any] = {"type": "string"}
        if cats: cat["enum"] = cats
        cat["description"] = _FIELD_DESCRIPTIONS["category"]
        mat_items: dict[str, Any] = {"type": "string"}
        if mats: mat_items["enum"] = mats
        col_items: dict[str, Any] = {"type": "string"}
        if cols: col_items["enum"] = cols
        return {
            "type": "object",
            "properties": {
                "category":    cat,
                "material":    {"type": "array", "items": mat_items, "description": _FIELD_DESCRIPTIONS["material"]},
                "color":       {"type": "array", "items": col_items, "description": _FIELD_DESCRIPTIONS["color"]},
                "price_level": {"type": "string", "enum": _PRICE_LEVELS, "description": _FIELD_DESCRIPTIONS["price_level"]},
                "min_price":   {"type": "number", "description": _FIELD_DESCRIPTIONS["min_price"]},
                "max_price":   {"type": "number", "description": _FIELD_DESCRIPTIONS["max_price"]},
                "search":      {"type": "string", "description": _FIELD_DESCRIPTIONS["search"]},
                "in_stock":    {"type": "boolean", "description": _FIELD_DESCRIPTIONS["in_stock"]},
            },
        }

    async def execute(self, user_id: int = 0, **kwargs: Any) -> dict[str, Any]:
        from app.core.semantic_config import resolve_price_level

        filters = {k: v for k, v in kwargs.items() if v is not None and k != "user_id"}

        if filters.get("price_level"):
            lvl_min, lvl_max = resolve_price_level(filters["price_level"])
            if lvl_min is not None and filters.get("min_price") is None:
                filters["min_price"] = lvl_min
            if lvl_max is not None and filters.get("max_price") is None:
                filters["max_price"] = lvl_max

        def _as_list(v: Any) -> list[str] | None:
            if v is None:
                return None
            if isinstance(v, str):
                return [v]
            if isinstance(v, list):
                return [str(x) for x in v if x]
            return None

        products = await self.provider.search_products(
            query=filters.get("search"),
            category=filters.get("category"),
            min_price=filters.get("min_price"),
            max_price=filters.get("max_price"),
            in_stock=filters.get("in_stock", True),
            material=_as_list(filters.get("material")),
            color=_as_list(filters.get("color")),
            limit=20,
        )

        short_products = [
            {"id": p["id"], "name": p["name"], "price": p["price"]}
            for p in products
        ]

        return {
            "action": "apply_filters",
            "filters": filters,
            "products": short_products,
            "instruction": "Catalog updated with the products listed above. "
            "Use these product IDs for any follow-up actions (add to cart, favorites, etc.). "
            "Do NOT list all products to the user — they already see them as cards in the UI. "
            "Just briefly confirm which filters were applied.",
        }
