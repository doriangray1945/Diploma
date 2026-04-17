from typing import Any

from core.tools.base import BaseTool


class GetProductDetailsTool(BaseTool):
    name = "get_product_details"
    description = "Get detailed information about a product by its ID"
    updates_context = {"open_product_id": "result.product.id"}
    parameters = {
        "type": "object",
        "properties": {
            "product_id": {
                "type": "integer",
                "description": "Product ID (numeric)",
            },
        },
        "required": ["product_id"],
    }

    async def execute(self, user_id: int = 0, **kwargs: Any) -> dict[str, Any]:
        product = await self.provider.get_product(kwargs["product_id"])
        if not product:
            return {"error": "Product not found"}
        return {"action": "show_product_details", "product": product}


class ApplyFiltersTool(BaseTool):
    name = "apply_filters"
    updates_context = {
        "last_search": "result",
        "visible_product_ids": "result.products[*].id",
        "current_filters": "result.filters",
    }
    description = (
        "Control the product catalog display. ALWAYS call this for ANY product request. "
        "Each call REPLACES all previous filters. Pass ALL desired filters every time. "
        "Call with NO arguments to clear filters and show all products. "
        "The catalog shows product cards with images and prices — do NOT list products yourself."
    )
    parameters = {
        "type": "object",
        "properties": {
            "search": {
                "type": "string",
                "description": "Уточняющий поиск внутри категории (например: детская, офисный, складной, угловой)",
            },
            "category": {
                "type": "string",
                "description": "Product category (exact value from available list)",
            },
            "min_price": {
                "type": "number",
                "description": "Minimum price",
            },
            "max_price": {
                "type": "number",
                "description": "Maximum price",
            },
            "in_stock": {
                "type": "boolean",
                "description": "Only in stock",
            },
        },
        "required": [],
    }

    async def execute(self, user_id: int = 0, **kwargs: Any) -> dict[str, Any]:
        filters = {k: v for k, v in kwargs.items() if v is not None and k != "user_id"}

        products = await self.provider.search_products(
            query=filters.get("search"),
            category=filters.get("category"),
            min_price=filters.get("min_price"),
            max_price=filters.get("max_price"),
            in_stock=filters.get("in_stock", True),
            limit=20,
        )

        short_products = [
            {"id": p["id"], "name": p["name"], "price": p["price"]}
            for p in products
        ]

        return {
            "action": "apply_filters",
            "filters": filters,
            "products": short_products,
            "instruction": "Catalog updated with the products listed above. "
            "Use these product IDs for any follow-up actions (add to cart, favorites, etc.). "
            "Do NOT list all products to the user — they already see them as cards in the UI. "
            "Just briefly confirm which filters were applied.",
        }
