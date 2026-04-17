from typing import Any

from core.tools.base import BaseTool, flatten_ids


class GetFavoritesTool(BaseTool):
    name = "get_favorites"
    description = "Get the user's favorites/wishlist. Call this FIRST before removing items."
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
    description = "Add one or multiple products to the user's favorites/wishlist"
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
    description = "Remove one or multiple products from the user's favorites/wishlist"
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
    description = "Remove ALL items from the user's favorites/wishlist"
    updates_context = {"favorites_summary": "result"}
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def execute(self, user_id: int = 0, **kwargs: Any) -> dict[str, Any]:
        result = await self.provider.clear_favorites(user_id)
        return {"action": "favorites_cleared", **result}