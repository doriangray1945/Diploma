"""Admin bulk-operation tools: stock/prices update + sales analytics.

Schema is built dynamically from `filter_options` (current DB catalog state)
via `_build_parameters` — adding/removing a category in DB shows up in the
next request's prompt without retrain. API-level enums (operation, period,
group_by, metric, sort) stay static — those are the contract, not data.
"""
from __future__ import annotations

from typing import Any

from app.llm.tools.base import BaseTool


# API-level enums (NOT catalog data — these are stable contracts)
_STOCK_OPS = ["set", "add", "subtract"]
_PRICE_OPS = ["discount", "markup", "set_price"]
_PERIODS = ["today", "week", "month", "quarter", "year", "custom"]
_GROUP_BY = ["product", "category", "color", "material", "price_level", "day"]
_METRICS = ["revenue", "units_sold", "orders_count", "avg_check"]
_SORT_DIRS = ["desc", "asc"]
_PRICE_LEVELS = ["budget", "mid", "premium"]

# Field descriptions — match dataset/generator.py:FIELD_DESCRIPTIONS
_FIELD_DESCRIPTIONS = {
    "category":     "Одна категория товара",
    "material":     "Материалы (массив, можно несколько)",
    "color":        "Цвета (массив, можно несколько)",
    "price_level":  "Семантический ценовой сегмент",
    "min_price":    "Минимальная цена в рублях",
    "max_price":    "Максимальная цена в рублях",
    "search":       "Описательные слова: стиль (лофт, минимализм), персона (детский, офисный), эмоция (уютный), конкретные сорта (дуб, велюр)",
    "in_stock":     "Только товары в наличии",
    "product_name": "Подстрока в имени товара",
    "product_ids":  "Конкретные ID товаров",
    "operation":    "Тип операции",
    "value":        "Значение (% для discount/markup, RUB для set_price)",
    "period":       "Период отчёта (today/week/month/quarter/year/custom)",
    "from_date":    "Начало периода YYYY-MM-DD (только при period=custom)",
    "to_date":      "Конец периода YYYY-MM-DD (только при period=custom)",
    "group_by":     "Измерение для группировки (product/category/color/material/price_level/day)",
    "metric":       "Какой показатель считаем (revenue/units_sold/orders_count/avg_check)",
    "sort":         "Направление сортировки (desc/asc)",
    "limit":        "Ограничение количества результатов",
}


def _build_admin_filter_schema(filter_options: dict[str, Any]) -> dict[str, Any]:
    """Builds the nested filter sub-object schema with dynamic enums from DB.
    Field/key order matches dataset/generator.py:_admin_filter_full_schema."""
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
        "minProperties": 1,
        "properties": {
            "category":     cat,
            "material":     {"type": "array", "items": mat_items, "description": _FIELD_DESCRIPTIONS["material"]},
            "color":        {"type": "array", "items": col_items, "description": _FIELD_DESCRIPTIONS["color"]},
            "price_level":  {"type": "string", "enum": _PRICE_LEVELS, "description": _FIELD_DESCRIPTIONS["price_level"]},
            "min_price":    {"type": "number", "description": _FIELD_DESCRIPTIONS["min_price"]},
            "max_price":    {"type": "number", "description": _FIELD_DESCRIPTIONS["max_price"]},
            "search":       {"type": "string", "description": _FIELD_DESCRIPTIONS["search"]},
            "in_stock":     {"type": "boolean", "description": _FIELD_DESCRIPTIONS["in_stock"]},
            "product_name": {"type": "string", "description": _FIELD_DESCRIPTIONS["product_name"]},
            "product_ids":  {"type": "array", "items": {"type": "integer"}, "description": _FIELD_DESCRIPTIONS["product_ids"]},
        },
    }


# Static fallback used when filter_options is unavailable (only at module load
# / boot inspection). Real prompts always go through _build_parameters.
_FALLBACK_FILTER_SCHEMA = _build_admin_filter_schema({})


class UpdateStockTool(BaseTool):
    name = "update_stock"
    description = "[ADMIN] Bulk-обновление остатков по фильтру (set/add/subtract)"
    role = "admin"
    parameters = {
        "type": "object",
        "properties": {
            "filter":    _FALLBACK_FILTER_SCHEMA,
            "operation": {"type": "string", "enum": _STOCK_OPS, "description": _FIELD_DESCRIPTIONS["operation"]},
            "quantity":  {"type": "integer", "minimum": 0, "description": "Количество для операции (число штук)"},
        },
        "required": ["filter", "operation", "quantity"],
    }

    def _build_parameters(self, filter_options: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "filter":    _build_admin_filter_schema(filter_options),
                "operation": {"type": "string", "enum": _STOCK_OPS, "description": _FIELD_DESCRIPTIONS["operation"]},
                "quantity":  {"type": "integer", "minimum": 0, "description": "Количество для операции (число штук)"},
            },
            "required": ["filter", "operation", "quantity"],
        }

    async def execute(self, user_id: int = 0, **kwargs: Any) -> dict[str, Any]:
        result = await self.provider.bulk_update_stock(
            filter=kwargs.get("filter", {}),
            operation=kwargs["operation"],
            quantity=kwargs["quantity"],
        )
        if "error" in result:
            return result
        return {"action": "stock_updated", **result}


class UpdatePricesTool(BaseTool):
    name = "update_prices"
    description = "[ADMIN] Bulk-изменение цен (discount/markup/set_price) по фильтру"
    role = "admin"
    parameters = {
        "type": "object",
        "properties": {
            "filter":    _FALLBACK_FILTER_SCHEMA,
            "operation": {"type": "string", "enum": _PRICE_OPS, "description": _FIELD_DESCRIPTIONS["operation"]},
            "value":     {"type": "integer", "description": _FIELD_DESCRIPTIONS["value"]},
        },
        "required": ["filter", "operation", "value"],
    }

    def _build_parameters(self, filter_options: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "filter":    _build_admin_filter_schema(filter_options),
                "operation": {"type": "string", "enum": _PRICE_OPS, "description": _FIELD_DESCRIPTIONS["operation"]},
                "value":     {"type": "integer", "description": _FIELD_DESCRIPTIONS["value"]},
            },
            "required": ["filter", "operation", "value"],
        }

    async def execute(self, user_id: int = 0, **kwargs: Any) -> dict[str, Any]:
        result = await self.provider.bulk_update_prices(
            filter=kwargs.get("filter", {}),
            operation=kwargs["operation"],
            value=kwargs["value"],
        )
        if "error" in result:
            return result
        return {"action": "prices_updated", **result}


class GetSalesAnalyticsTool(BaseTool):
    name = "get_sales_analytics"
    description = "[ADMIN] Гибкая аналитика продаж по периоду и группировке"
    role = "admin"
    parameters = {
        "type": "object",
        "properties": {
            "period":    {"type": "string", "enum": _PERIODS, "description": _FIELD_DESCRIPTIONS["period"]},
            "from_date": {"type": "string", "description": _FIELD_DESCRIPTIONS["from_date"]},
            "to_date":   {"type": "string", "description": _FIELD_DESCRIPTIONS["to_date"]},
            "group_by":  {"type": "string", "enum": _GROUP_BY, "description": _FIELD_DESCRIPTIONS["group_by"]},
            "metric":    {"type": "string", "enum": _METRICS, "description": _FIELD_DESCRIPTIONS["metric"]},
            "sort":      {"type": "string", "enum": _SORT_DIRS, "description": _FIELD_DESCRIPTIONS["sort"]},
            "limit":     {"type": "integer", "description": _FIELD_DESCRIPTIONS["limit"]},
            "filter":    _FALLBACK_FILTER_SCHEMA,
        },
        "required": ["period", "group_by", "metric"],
    }

    def _build_parameters(self, filter_options: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "period":    {"type": "string", "enum": _PERIODS, "description": _FIELD_DESCRIPTIONS["period"]},
                "from_date": {"type": "string", "description": _FIELD_DESCRIPTIONS["from_date"]},
                "to_date":   {"type": "string", "description": _FIELD_DESCRIPTIONS["to_date"]},
                "group_by":  {"type": "string", "enum": _GROUP_BY, "description": _FIELD_DESCRIPTIONS["group_by"]},
                "metric":    {"type": "string", "enum": _METRICS, "description": _FIELD_DESCRIPTIONS["metric"]},
                "sort":      {"type": "string", "enum": _SORT_DIRS, "description": _FIELD_DESCRIPTIONS["sort"]},
                "limit":     {"type": "integer", "description": _FIELD_DESCRIPTIONS["limit"]},
                "filter":    _build_admin_filter_schema(filter_options),
            },
            "required": ["period", "group_by", "metric"],
        }

    async def execute(self, user_id: int = 0, **kwargs: Any) -> dict[str, Any]:
        clean = {k: v for k, v in kwargs.items() if v is not None and k != "user_id"}
        result = await self.provider.query_sales_analytics(**clean)
        if "error" in result:
            return result
        return {"action": "sales_analytics", **result}
