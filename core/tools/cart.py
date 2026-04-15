from typing import Any

from core.tools.base import BaseTool


class AddToCartTool(BaseTool):
    name = "add_to_cart"
    description = "Add one or multiple products to the user's shopping cart"
    parameters = {
        "type": "object",
        "properties": {
            "product_id": {
                "type": "integer",
                "description": "Single product ID to add",
            },
            "product_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Multiple product IDs to add at once",
            },
            "quantity": {
                "type": "integer",
                "description": "Quantity per product (default 1)",
            },
        },
        "required": [],
    }

    async def execute(self, user_id: int = 0, **kwargs: Any) -> dict[str, Any]:
        quantity = kwargs.get("quantity", 1)
        ids = kwargs.get("product_ids") or []
        if kwargs.get("product_id"):
            ids.append(kwargs["product_id"])

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


class GetCartTool(BaseTool):
    name = "get_cart"
    description = "Get the contents of the user's shopping cart"
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def execute(self, user_id: int = 0, **kwargs: Any) -> dict[str, Any]:
        result = await self.provider.get_cart(user_id)
        return {"action": "show_cart", **result}