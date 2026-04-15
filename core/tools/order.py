from typing import Any

from core.tools.base import BaseTool


class CreateOrderTool(BaseTool):
    name = "create_order"
    description = "Create an order from the shopping cart. Ask user for address and phone first."
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

    async def execute(self, user_id: int = 0, **kwargs: Any) -> dict[str, Any]:
        address = kwargs.pop("address", "")
        phone = kwargs.pop("phone", "")
        result = await self.provider.create_order(user_id, address, phone)
        if "error" in result:
            return result
        return {"action": "order_created", **result}


class ModifyOrderTool(BaseTool):
    name = "modify_order"
    description = "Modify an existing order (address, status, cancellation)"
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

    async def execute(self, user_id: int = 0, **kwargs: Any) -> dict[str, Any]:
        order_id = kwargs.pop("order_id")
        result = await self.provider.modify_order(order_id, **kwargs)
        if "error" in result:
            return result
        return {"action": "order_modified", **result}