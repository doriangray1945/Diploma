from typing import Any

from core.tools.base import BaseTool


class GetProductDetailsTool(BaseTool):
    name = "get_product_details"
    description = "Открыть карточку товара с подробной информацией по его ID"

    def skeleton_examples(self):
        return ["открой товар", "покажи детали товара", "подробнее про товар"]
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

    def param_schema(self, filter_options=None, session_context=None):
        # Restrict product_id to currently visible products + the one already open.
        allowed: list[int] = []
        if session_context is not None:
            allowed = list(session_context.visible_product_ids or [])
            if session_context.open_product_id is not None:
                if session_context.open_product_id not in allowed:
                    allowed.append(session_context.open_product_id)
        pid_schema: dict[str, Any] = {"type": "integer"}
        if allowed:
            pid_schema["enum"] = allowed
        return {
            "type": "object",
            "properties": {"product_id": pid_schema},
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
        "Найти/показать товары в каталоге по фильтрам "
        "(категория, поиск, цена). Каждый вызов ЗАМЕНЯЕТ предыдущие фильтры — "
        "передавай все нужные фильтры сразу. Без аргументов — показать все товары."
    )

    def skeleton_examples(self):
        return [
            "покажи диваны", "найди столы до 30000",
            "предложи кровати детские", "что есть из стульев",
            "покажи все товары",
        ]
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

    def param_schema(self, filter_options=None, session_context=None):
        cat_schema: dict[str, Any] = {"type": "string"}
        if filter_options and filter_options.get("categories"):
            cat_schema["enum"] = list(filter_options["categories"])
        return {
            "type": "object",
            "properties": {
                "search": {
                    "type": "string",
                    "maxLength": 64,
                    "description": (
                        "Уточняющий запрос ВНУТРИ категории — обычно это "
                        "прилагательное-определение к категории "
                        "(детская, офисный, складной, угловой, деревянный). "
                        "ОБЯЗАТЕЛЬНО заполняй когда в запросе есть подобное "
                        "прилагательное (например «детские кровати» → search='детская')."
                    ),
                },
                "category": cat_schema,
                "min_price": {"type": "number", "minimum": 0},
                "max_price": {"type": "number", "minimum": 0},
                "in_stock": {"type": "boolean"},
            },
            "required": [],
        }

    def few_shot(self):
        return [
            {"user": "диваны до 50000",
             "args": {"category": "Диваны", "max_price": 50000}},
            {"user": "офисные стулья от 5000 до 20000",
             "args": {"category": "Стулья", "search": "офисный",
                      "min_price": 5000, "max_price": 20000}},
            {"user": "предложи кровати детские",
             "args": {"category": "Кровати", "search": "детская"}},
            {"user": "складные столы",
             "args": {"category": "Столы", "search": "складной"}},
            {"user": "покажи угловые диваны",
             "args": {"category": "Диваны", "search": "угловой"}},
        ]

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
