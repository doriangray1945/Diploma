from typing import Any

from app.llm.tools.base import BaseTool, flatten_ids


_QUANTIFIERS = ["all", "first_n", "last_n", "remaining", "specific"]

_FIELD_DESCRIPTIONS = {
    "quantifier":   "Какие товары выбрать из видимых (all/first_n/last_n/remaining/specific)",
    "n":            "Число РАЗНЫХ товаров (когда quantifier=first_n/last_n)",
    "product_ids":  "Конкретные ID товаров",
    "category":     "Одна категория товара",
    "color":        "Цвета (массив, можно несколько)",
    "material":     "Материалы (массив, можно несколько)",
    "price_level":  "Ценовой уровень (budget/mid/premium)",
    "product_name": "Подстрока в имени товара",
    "all":          "Очистить всё (для filter в remove_from_*)",
    "add_filter":   "Сузить выбор variant'ов товара по цвету/материалу/ценовому уровню",
}


class AddToFavoritesTool(BaseTool):
    name = "add_to_favorites"
    description = "Добавить товары в избранное (с указанием quantifier)"

    updates_context = {"favorites_summary": "result"}
    parameters = {
        "type": "object",
        "properties": {
            "quantifier":  {"type": "string", "enum": _QUANTIFIERS, "description": _FIELD_DESCRIPTIONS["quantifier"]},
            "n":           {"type": "integer", "description": _FIELD_DESCRIPTIONS["n"]},
            "product_ids": {"type": "array", "items": {"type": "integer"}, "description": _FIELD_DESCRIPTIONS["product_ids"]},
            "filter": {
                "type": "object",
                "description": _FIELD_DESCRIPTIONS["add_filter"],
                "properties": {
                    "color":       {"type": "array", "items": {"type": "string"}, "description": _FIELD_DESCRIPTIONS["color"]},
                    "material":    {"type": "array", "items": {"type": "string"}, "description": _FIELD_DESCRIPTIONS["material"]},
                    "price_level": {"type": "string", "enum": ["budget", "mid", "premium"], "description": _FIELD_DESCRIPTIONS["price_level"]},
                },
            },
        },
    }

    def _build_parameters(self, filter_options: dict[str, Any]) -> dict[str, Any]:
        cols = list(filter_options.get("colors") or [])
        mats = list(filter_options.get("materials") or [])
        col_items: dict[str, Any] = {"type": "string"}
        if cols: col_items["enum"] = cols
        mat_items: dict[str, Any] = {"type": "string"}
        if mats: mat_items["enum"] = mats
        return {
            "type": "object",
            "properties": {
                "quantifier":  {"type": "string", "enum": _QUANTIFIERS, "description": _FIELD_DESCRIPTIONS["quantifier"]},
                "n":           {"type": "integer", "description": _FIELD_DESCRIPTIONS["n"]},
                "product_ids": {"type": "array", "items": {"type": "integer"}, "description": _FIELD_DESCRIPTIONS["product_ids"]},
                "filter": {
                    "type": "object",
                    "description": _FIELD_DESCRIPTIONS["add_filter"],
                    "properties": {
                        "color":       {"type": "array", "items": col_items, "description": _FIELD_DESCRIPTIONS["color"]},
                        "material":    {"type": "array", "items": mat_items, "description": _FIELD_DESCRIPTIONS["material"]},
                        "price_level": {"type": "string", "enum": ["budget", "mid", "premium"], "description": _FIELD_DESCRIPTIONS["price_level"]},
                    },
                },
            },
        }

    async def execute(self, user_id: int = 0, **kwargs: Any) -> dict[str, Any]:
        ids = flatten_ids(kwargs.get("product_ids"))
        if kwargs.get("product_id"):
            ids.append(int(kwargs["product_id"]))

        if not ids:
            return {"error": "product_id or product_ids is required"}

        flt = kwargs.get("filter")
        variant_filter = flt if isinstance(flt, dict) and flt else None

        results = []
        errors = []
        for pid in ids:
            result = await self.provider.add_to_favorites(
                user_id, pid, variant_filter=variant_filter
            )
            if "error" in result:
                errors.append({"product_id": pid, "error": result["error"]})
            else:
                results.append(result)

        return {
            "action": "added_to_favorites",
            "added": results,
            "errors": errors,
            "count": len(results),
        }


class RemoveFromFavoritesTool(BaseTool):
    name = "remove_from_favorites"
    description = "Удалить товары из избранного по фильтру"

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

        result = await self.provider.remove_favorites_by_filter(user_id, flt)
        return {
            "action": "removed_from_favorites",
            **result,
        }


class ClearFavoritesTool(BaseTool):
    name = "clear_favorites"
    description = "Очистить избранное полностью"

    updates_context = {"favorites_summary": "result"}
    parameters = {"type": "object", "properties": {}}

    async def execute(self, user_id: int = 0, **kwargs: Any) -> dict[str, Any]:
        result = await self.provider.clear_favorites(user_id)
        return {"action": "favorites_cleared", **result}
