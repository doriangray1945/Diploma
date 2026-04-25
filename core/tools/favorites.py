from typing import Any

from core.tools.base import BaseTool, flatten_ids


class GetFavoritesTool(BaseTool):
    name = "get_favorites"
    description = "Показать избранное (список желаемых товаров)"

    def skeleton_examples(self):
        return ["что в избранном", "покажи wishlist"]
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def execute(self, user_id: int = 0, **kwargs: Any) -> dict[str, Any]:
        items = await self.provider.get_favorites(user_id)
        if not items:
            return {"favorites": [], "message": "Favorites list is empty"}
        return {"favorites": items, "count": len(items)}


class AddToFavoritesTool(BaseTool):
    name = "add_to_favorites"
    description = "Добавить товары в избранное (wishlist)"

    def skeleton_examples(self):
        return [
            "добавь в избранное", "сохрани на потом",
            "в wishlist", "запомни эти товары",
        ]
    updates_context = {"favorites_summary": "result"}
    parameters = {
        "type": "object",
        "properties": {
            "product_id": {
                "type": "integer",
                "description": "Single product ID",
            },
            "product_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Multiple product IDs to add at once",
            },
        },
        "required": [],
    }

    def param_schema(self, filter_options=None, session_context=None):
        visible: list[int] = []
        if session_context is not None:
            visible = list(session_context.visible_product_ids or [])
        ids_schema: dict[str, Any] = {"type": "array", "items": {"type": "integer"}}
        if visible:
            ids_schema["items"] = {"type": "integer", "enum": visible}
            ids_schema["minItems"] = 1
        return {
            "type": "object",
            "properties": {"product_ids": ids_schema},
            "required": ["product_ids"],
        }

    def few_shot(self):
        return [
            {"user": "в избранное первые 3",
             "args": {"product_ids": "$context.visible_product_ids"}},
        ]

    async def execute(self, user_id: int = 0, **kwargs: Any) -> dict[str, Any]:
        ids = flatten_ids(kwargs.get("product_ids"))
        if kwargs.get("product_id"):
            ids.append(int(kwargs["product_id"]))

        if not ids:
            return {"error": "product_id or product_ids is required"}

        results = []
        errors = []
        for pid in ids:
            result = await self.provider.add_to_favorites(user_id, pid)
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
    description = "Удалить товары из избранного"

    def skeleton_examples(self):
        return ["убери из избранного", "удали из wishlist"]
    parameters = {
        "type": "object",
        "properties": {
            "product_id": {
                "type": "integer",
                "description": "Single product ID",
            },
            "product_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Multiple product IDs to remove at once",
            },
        },
        "required": [],
    }

    def param_schema(self, filter_options=None, session_context=None):
        # Restrict to currently-favorited product ids when known.
        allowed: list[int] = []
        if session_context is not None and session_context.favorites_summary:
            fav = session_context.favorites_summary
            for entry in fav.get("favorites", []) or fav.get("items", []):
                if isinstance(entry, dict) and "product_id" in entry:
                    allowed.append(int(entry["product_id"]))
                elif isinstance(entry, dict) and "id" in entry:
                    allowed.append(int(entry["id"]))
        ids_schema: dict[str, Any] = {"type": "array", "items": {"type": "integer"}}
        if allowed:
            ids_schema["items"] = {"type": "integer", "enum": allowed}
            ids_schema["minItems"] = 1
        return {
            "type": "object",
            "properties": {"product_ids": ids_schema},
            "required": ["product_ids"],
        }

    async def execute(self, user_id: int = 0, **kwargs: Any) -> dict[str, Any]:
        ids = flatten_ids(kwargs.get("product_ids"))
        if kwargs.get("product_id"):
            ids.append(int(kwargs["product_id"]))

        if not ids:
            return {"error": "product_id or product_ids is required"}

        results = []
        errors = []
        for pid in ids:
            result = await self.provider.remove_from_favorites(user_id, pid)
            if "error" in result:
                errors.append({"product_id": pid, "error": result["error"]})
            else:
                results.append(result)

        return {
            "action": "removed_from_favorites",
            "removed": results,
            "errors": errors,
            "count": len(results),
        }


class ClearFavoritesTool(BaseTool):
    name = "clear_favorites"
    description = "Очистить избранное (удалить все товары из wishlist)"

    def skeleton_examples(self):
        return ["очисти избранное", "удали все из wishlist"]
    updates_context = {"favorites_summary": "result"}
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def execute(self, user_id: int = 0, **kwargs: Any) -> dict[str, Any]:
        result = await self.provider.clear_favorites(user_id)
        return {"action": "favorites_cleared", **result}