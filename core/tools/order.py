from typing import Any

from core.tools.base import BaseTool


class CreateOrderTool(BaseTool):
    name = "create_order"
    description = (
        "Оформить заказ из корзины. "
        "ТРЕБУЕТ адрес доставки и номер телефона — попроси их у пользователя если их нет."
    )

    def skeleton_examples(self):
        return ["оформи заказ", "сделай заказ", "купить корзину"]
    parameters = {
        "type": "object",
        "properties": {
            "address": {
                "type": "string",
                "description": "Delivery address",
            },
            "phone": {
                "type": "string",
                "description": "Contact phone number",
            },
        },
        "required": ["address", "phone"],
    }

    def param_schema(self, filter_options=None, session_context=None):
        # Ollama 0.20.7's JSON-schema-to-grammar converter rejects `pattern`,
        # so phone format is validated Python-side in plan_executor.
        return {
            "type": "object",
            "properties": {
                "address": {"type": "string", "minLength": 5},
                "phone": {"type": "string"},
            },
            "required": ["address", "phone"],
        }

    async def execute(self, user_id: int = 0, **kwargs: Any) -> dict[str, Any]:
        address = kwargs.pop("address", "")
        phone = kwargs.pop("phone", "")
        result = await self.provider.create_order(user_id, address, phone)
        if "error" in result:
            return result
        return {"action": "order_created", **result}


class ModifyOrderTool(BaseTool):
    name = "modify_order"
    description = (
        "Изменить или отменить УЖЕ ОФОРМЛЕННЫЙ заказ по его номеру (order_id). "
        "НЕ для добавления товаров в корзину — для корзины используй add_to_cart."
    )

    def skeleton_examples(self):
        return [
            "отмени заказ #123", "измени адрес заказа №5",
            "поменяй статус заказа",
        ]
    parameters = {
        "type": "object",
        "properties": {
            "order_id": {
                "type": "integer",
                "description": "Order ID",
            },
            "address": {
                "type": "string",
                "description": "New delivery address",
            },
            "status": {
                "type": "string",
                "description": "New status (e.g. cancelled)",
            },
        },
        "required": ["order_id"],
    }

    def param_schema(self, filter_options=None, session_context=None):
        return {
            "type": "object",
            "properties": {
                "order_id": {"type": "integer", "minimum": 1},
                "address": {"type": "string", "minLength": 5},
                "status": {"type": "string"},
            },
            "required": ["order_id"],
        }

    async def execute(self, user_id: int = 0, **kwargs: Any) -> dict[str, Any]:
        order_id = kwargs.pop("order_id")
        result = await self.provider.modify_order(order_id, **kwargs)
        if "error" in result:
            return result
        return {"action": "order_modified", **result}