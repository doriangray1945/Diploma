from typing import Any

from core.tools.base import BaseTool


class AddProductTool(BaseTool):
    name = "add_product"
    description = "Добавить новый товар в каталог (только для админов)"
    role = "admin"
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Product name"},
            "description": {"type": "string", "description": "Product description"},
            "price": {"type": "number", "description": "Price"},
            "category": {"type": "string", "description": "Category"},
            "stock_quantity": {"type": "integer", "description": "Stock quantity"},
        },
        "required": ["name", "price", "category"],
    }

    async def execute(self, user_id: int = 0, **kwargs: Any) -> dict[str, Any]:
        result = await self.provider.add_product(**kwargs)
        if "error" in result:
            return result
        return {"action": "product_added", **result}


class UpdateProductTool(BaseTool):
    name = "update_product"
    description = "Изменить данные товара в каталоге (только для админов)"
    role = "admin"
    parameters = {
        "type": "object",
        "properties": {
            "product_id": {"type": "integer", "description": "Product ID"},
            "name": {"type": "string", "description": "New name"},
            "price": {"type": "number", "description": "New price"},
            "stock_quantity": {"type": "integer", "description": "New stock quantity"},
        },
        "required": ["product_id"],
    }

    async def execute(self, user_id: int = 0, **kwargs: Any) -> dict[str, Any]:
        product_id = kwargs.pop("product_id")
        result = await self.provider.update_product(product_id, **kwargs)
        if "error" in result:
            return result
        return {"action": "product_updated", **result}


class DeleteProductTool(BaseTool):
    name = "delete_product"
    description = "Удалить товар из каталога (только для админов)"
    role = "admin"
    parameters = {
        "type": "object",
        "properties": {
            "product_id": {"type": "integer", "description": "Product ID"},
        },
        "required": ["product_id"],
    }

    async def execute(self, user_id: int = 0, **kwargs: Any) -> dict[str, Any]:
        result = await self.provider.delete_product(kwargs["product_id"])
        if "error" in result:
            return result
        return {"action": "product_deleted", **result}