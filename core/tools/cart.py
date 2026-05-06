from typing import Any

from core.tools.base import BaseTool, flatten_ids


# API-level enum (selection contract — not catalog data)
_QUANTIFIERS = ["all", "first_n", "last_n", "remaining", "specific"]

# Field descriptions — match dataset/generator.py:FIELD_DESCRIPTIONS
_FIELD_DESCRIPTIONS = {
    "quantifier":   "Какие товары выбрать из видимых (all/first_n/last_n/remaining/specific)",
    "n":            "Число РАЗНЫХ товаров (когда quantifier=first_n/last_n)",
    "product_ids":  "Конкретные ID товаров",
    "quantity":     "Число ШТУК каждого выбранного товара (default 1)",
    "category":     "Одна категория товара",
    "color":        "Цвета (массив, можно несколько)",
    "material":     "Материалы (массив, можно несколько)",
    "product_name": "Подстрока в имени товара",
    "all":          "Очистить всё (для filter в remove_from_*)",
}


class AddToCartTool(BaseTool):
    name = "add_to_cart"
    description = "Добавить товары в корзину (с указанием количества)"

    updates_context = {"cart_summary": "result"}
    parameters = {
        "type": "object",
        "properties": {
            "quantifier":  {"type": "string", "enum": _QUANTIFIERS, "description": _FIELD_DESCRIPTIONS["quantifier"]},
            "n":           {"type": "integer", "description": _FIELD_DESCRIPTIONS["n"]},
            "product_ids": {"type": "array", "items": {"type": "integer"}, "description": _FIELD_DESCRIPTIONS["product_ids"]},
            "quantity":    {"type": "integer", "description": _FIELD_DESCRIPTIONS["quantity"]},
        },
    }

    async def execute(self, user_id: int = 0, **kwargs: Any) -> dict[str, Any]:
        quantity = kwargs.get("quantity", 1)
        ids = flatten_ids(kwargs.get("product_ids"))
        if kwargs.get("product_id"):
            ids.append(int(kwargs["product_id"]))

        if not ids:
            return {"error": "product_id or product_ids is required"}

        results = []
        errors = []
        for pid in ids:
            result = await self.provider.add_to_cart(user_id, pid, quantity)
            if "error" in result:
                errors.append({"product_id": pid, "error": result["error"]})
            else:
                results.append(result)

        return {
            "action": "added_to_cart",
            "added": results,
            "errors": errors,
            "count": len(results),
        }


class ClearCartTool(BaseTool):
    name = "clear_cart"
    description = "Очистить корзину полностью"

    updates_context = {"cart_summary": "result"}
    parameters = {"type": "object", "properties": {}}

    async def execute(self, user_id: int = 0, **kwargs: Any) -> dict[str, Any]:
        result = await self.provider.clear_cart(user_id)
        return {"action": "cart_cleared", **result}


class RemoveFromCartTool(BaseTool):
    name = "remove_from_cart"
    description = "Удалить товары из корзины по фильтру"
    updates_context = {"cart_summary": "result"}

    # Static fallback (when filter_options is empty)
    parameters = {
        "type": "object",
        "properties": {
            "filter": {
                "type": "object",
                "minProperties": 1,
                "properties": {
                    "category":     {"type": "string", "description": _FIELD_DESCRIPTIONS["category"]},
                    "color":        {"type": "array", "items": {"type": "string"}, "description": _FIELD_DESCRIPTIONS["color"]},
                    "material":     {"type": "array", "items": {"type": "string"}, "description": _FIELD_DESCRIPTIONS["material"]},
                    "product_name": {"type": "string", "description": _FIELD_DESCRIPTIONS["product_name"]},
                    "all":          {"type": "boolean", "description": _FIELD_DESCRIPTIONS["all"]},
                },
            },
        },
        "required": ["filter"],
    }

    def _build_parameters(self, filter_options: dict[str, Any]) -> dict[str, Any]:
        cats = list(filter_options.get("categories") or [])
        cols = list(filter_options.get("colors") or [])
        mats = list(filter_options.get("materials") or [])
        cat: dict[str, Any] = {"type": "string"}
        if cats: cat["enum"] = cats
        cat["description"] = _FIELD_DESCRIPTIONS["category"]
        col_items: dict[str, Any] = {"type": "string"}
        if cols: col_items["enum"] = cols
        mat_items: dict[str, Any] = {"type": "string"}
        if mats: mat_items["enum"] = mats
        return {
            "type": "object",
            "properties": {
                "filter": {
                    "type": "object",
                    "minProperties": 1,
                    "properties": {
                        "category":     cat,
                        "color":        {"type": "array", "items": col_items, "description": _FIELD_DESCRIPTIONS["color"]},
                        "material":     {"type": "array", "items": mat_items, "description": _FIELD_DESCRIPTIONS["material"]},
                        "product_name": {"type": "string", "description": _FIELD_DESCRIPTIONS["product_name"]},
                        "all":          {"type": "boolean", "description": _FIELD_DESCRIPTIONS["all"]},
                    },
                },
            },
            "required": ["filter"],
        }

    async def execute(self, user_id: int = 0, **kwargs: Any) -> dict[str, Any]:
        flt = kwargs.get("filter") or {}
        if not isinstance(flt, dict) or not flt:
            return {"error": "filter is required"}
        result = await self.provider.remove_cart_by_filter(user_id, flt)
        return {
            "action": "removed_from_cart",
            **result,
        }
