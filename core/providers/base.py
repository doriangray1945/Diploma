from typing import Protocol, Any


class DataProvider(Protocol):
    # Catalog
    async def search_products(
        self,
        query: str | None = None,
        category: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        in_stock: bool = True,
        limit: int = 5,
        **filters: Any,
    ) -> list[dict[str, Any]]: ...

    async def get_product(self, product_id: int) -> dict[str, Any] | None: ...

    async def search_similar(
        self, embedding: list[float], limit: int = 5
    ) -> list[dict[str, Any]]: ...

    # Cart
    async def add_to_cart(
        self, user_id: int, product_id: int, quantity: int = 1
    ) -> dict[str, Any]: ...

    async def get_cart(self, user_id: int) -> dict[str, Any]: ...

    async def remove_from_cart(self, user_id: int, item_id: int) -> dict[str, Any]: ...

    # Orders
    async def create_order(
        self, user_id: int, address: str, phone: str
    ) -> dict[str, Any]: ...

    async def get_orders(self, user_id: int) -> list[dict[str, Any]]: ...

    async def modify_order(
        self, order_id: int, **updates: Any
    ) -> dict[str, Any]: ...

    # Favorites
    async def get_favorites(self, user_id: int) -> list[dict[str, Any]]: ...

    async def add_to_favorites(
        self, user_id: int, product_id: int
    ) -> dict[str, Any]: ...

    async def remove_from_favorites(
        self, user_id: int, product_id: int
    ) -> dict[str, Any]: ...

    # Admin
    async def add_product(self, **product_data: Any) -> dict[str, Any]: ...

    async def update_product(
        self, product_id: int, **updates: Any
    ) -> dict[str, Any]: ...

    async def delete_product(self, product_id: int) -> dict[str, Any]: ...
