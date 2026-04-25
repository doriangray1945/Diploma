from typing import Any

from core.tools.base import BaseTool, flatten_ids


class AddToCartTool(BaseTool):
    name = "add_to_cart"
    description = "Добавить товары в корзину пользователя (с указанием количества)"

    def skeleton_examples(self):
        return [
            "добавь в корзину", "положи в корзину",
            "купи", "возьму это", "добавь все по 2 шт в корзину",
        ]
    updates_context = {"cart_summary": "result"}
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
            "properties": {
                "product_ids": ids_schema,
                "quantity": {"type": "integer", "minimum": 1, "maximum": 99},
            },
            "required": ["product_ids"],
        }

    def few_shot(self):
        return [
            {"user": "добавь все по 2 шт",
             "args": {"product_ids": "$context.visible_product_ids", "quantity": 2}},
        ]

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


class GetCartTool(BaseTool):
    name = "get_cart"
    description = "Показать содержимое корзины пользователя"

    def skeleton_examples(self):
        return ["что в корзине", "покажи корзину"]
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def execute(self, user_id: int = 0, **kwargs: Any) -> dict[str, Any]:
        result = await self.provider.get_cart(user_id)
        return {"action": "show_cart", **result}


class ClearCartTool(BaseTool):
    name = "clear_cart"
    description = "Очистить корзину (удалить все товары)"

    def skeleton_examples(self):
        return ["очисти корзину", "удали всё из корзины"]
    updates_context = {"cart_summary": "result"}
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def execute(self, user_id: int = 0, **kwargs: Any) -> dict[str, Any]:
        result = await self.provider.clear_cart(user_id)
        return {"action": "cart_cleared", **result}