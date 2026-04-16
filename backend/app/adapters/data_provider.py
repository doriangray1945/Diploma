from typing import Any

from sqlalchemy import select, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Product, CartItem, Order, OrderItem, Favorite


class PostgresDataProvider:
    """Implements DataProvider protocol using SQLAlchemy + PostgreSQL."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Catalog ──────────────────────────────────────────────────

    async def search_products(
        self,
        query: str | None = None,
        category: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        in_stock: bool = True,
        limit: int = 5,
        **filters: Any,
    ) -> list[dict[str, Any]]:
        q = select(Product)

        if query:
            pattern = f"%{query}%"
            q = q.where(
                or_(
                    Product.name.ilike(pattern),
                    Product.description.ilike(pattern),
                )
            )
        if category:
            q = q.where(Product.category.ilike(f"%{category}%"))
        if min_price is not None:
            q = q.where(Product.price >= min_price)
        if max_price is not None:
            q = q.where(Product.price <= max_price)
        if in_stock:
            q = q.where(Product.in_stock == True)

        # Domain-specific filters (e.g. color for furniture)
        color = filters.get("color")
        if color:
            q = q.where(Product.color.ilike(f"%{color}%"))

        q = q.limit(limit)
        result = await self.db.execute(q)
        products = result.scalars().all()

        return [self._product_to_dict(p) for p in products]

    async def get_product(self, product_id: int) -> dict[str, Any] | None:
        try:
            product_id = int(product_id)
        except (TypeError, ValueError):
            return None
        try:
            result = await self.db.execute(
                select(Product).where(Product.id == product_id)
            )
            product = result.scalar_one_or_none()
        except Exception:
            await self.db.rollback()
            return None
        if not product:
            return None
        return self._product_to_dict(product, detailed=True)

    # ── Cart ─────────────────────────────────────────────────────

    async def add_to_cart(
        self, user_id: int, product_id: int, quantity: int = 1
    ) -> dict[str, Any]:
        try:
            product_id = int(product_id)
            quantity = int(quantity)
        except (TypeError, ValueError):
            return {"error": "Некорректные параметры"}
        result = await self.db.execute(
            select(Product).where(Product.id == product_id)
        )
        product = result.scalar_one_or_none()

        if not product:
            return {"error": "Товар не найден"}
        if not product.in_stock:
            return {"error": "Товар не в наличии"}

        cart_result = await self.db.execute(
            select(CartItem).where(
                CartItem.user_id == user_id,
                CartItem.product_id == product_id,
            )
        )
        existing = cart_result.scalar_one_or_none()

        if existing:
            existing.quantity += quantity
        else:
            self.db.add(
                CartItem(
                    user_id=user_id,
                    product_id=product_id,
                    quantity=quantity,
                )
            )
        await self.db.commit()

        return {
            "product_id": product_id,
            "product_name": product.name,
            "quantity": quantity,
            "price": float(product.price),
        }

    async def get_cart(self, user_id: int) -> dict[str, Any]:
        result = await self.db.execute(
            select(CartItem)
            .where(CartItem.user_id == user_id)
            .options(selectinload(CartItem.product))
        )
        items = result.scalars().all()

        total = 0.0
        cart_items = []
        for item in items:
            subtotal = float(item.product.price) * item.quantity
            total += subtotal
            cart_items.append({
                "id": item.id,
                "product_id": item.product_id,
                "product_name": item.product.name,
                "quantity": item.quantity,
                "price": float(item.product.price),
                "subtotal": subtotal,
            })

        return {
            "items": cart_items,
            "total": round(total, 2),
            "items_count": len(cart_items),
        }

    async def remove_from_cart(
        self, user_id: int, item_id: int
    ) -> dict[str, Any]:
        result = await self.db.execute(
            select(CartItem).where(
                CartItem.id == item_id,
                CartItem.user_id == user_id,
            )
        )
        item = result.scalar_one_or_none()
        if not item:
            return {"error": "Элемент корзины не найден"}

        await self.db.delete(item)
        await self.db.commit()
        return {"removed": True}

    # ── Orders ───────────────────────────────────────────────────

    async def create_order(
        self, user_id: int, address: str, phone: str
    ) -> dict[str, Any]:
        cart_result = await self.db.execute(
            select(CartItem)
            .where(CartItem.user_id == user_id)
            .options(selectinload(CartItem.product))
        )
        cart_items = cart_result.scalars().all()

        if not cart_items:
            return {"error": "Корзина пуста"}

        total = 0.0
        order_items = []
        for item in cart_items:
            item_total = float(item.product.price) * item.quantity
            total += item_total
            order_items.append(
                OrderItem(
                    product_id=item.product_id,
                    product_name=item.product.name,
                    quantity=item.quantity,
                    price=float(item.product.price),
                )
            )

        order = Order(
            user_id=user_id,
            status="pending",
            total=total,
            address=address,
            phone=phone,
        )
        self.db.add(order)
        await self.db.flush()

        for oi in order_items:
            oi.order_id = order.id
            self.db.add(oi)

        for ci in cart_items:
            await self.db.delete(ci)

        await self.db.commit()

        return {
            "order_id": order.id,
            "total": round(total, 2),
            "status": "pending",
            "message": f"Заказ №{order.id} успешно создан! Сумма: {total:.2f} руб.",
        }

    async def get_orders(self, user_id: int) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(Order)
            .where(Order.user_id == user_id)
            .order_by(Order.created_at.desc())
        )
        orders = result.scalars().all()
        return [
            {
                "id": o.id,
                "status": o.status,
                "total": float(o.total),
                "address": o.address,
                "created_at": str(o.created_at),
            }
            for o in orders
        ]

    async def modify_order(
        self, order_id: int, **updates: Any
    ) -> dict[str, Any]:
        result = await self.db.execute(
            select(Order).where(Order.id == order_id)
        )
        order = result.scalar_one_or_none()
        if not order:
            return {"error": "Заказ не найден"}

        for key, value in updates.items():
            if hasattr(order, key) and value is not None:
                setattr(order, key, value)

        await self.db.commit()
        return {
            "order_id": order.id,
            "status": order.status,
            "message": f"Заказ №{order.id} обновлён",
        }

    # ── Admin ────────────────────────────────────────────────────

    async def add_product(self, **product_data: Any) -> dict[str, Any]:
        product = Product(
            name=product_data.get("name", ""),
            description=product_data.get("description", ""),
            price=product_data.get("price", 0),
            category=product_data.get("category", ""),
            color=product_data.get("color"),
            stock_quantity=product_data.get("stock_quantity", 0),
            in_stock=product_data.get("stock_quantity", 0) > 0,
        )
        self.db.add(product)
        await self.db.commit()
        await self.db.refresh(product)

        return {
            "product_id": product.id,
            "name": product.name,
            "message": f"Товар '{product.name}' добавлен (ID: {product.id})",
        }

    async def update_product(
        self, product_id: int, **updates: Any
    ) -> dict[str, Any]:
        result = await self.db.execute(
            select(Product).where(Product.id == product_id)
        )
        product = result.scalar_one_or_none()
        if not product:
            return {"error": "Товар не найден"}

        for key, value in updates.items():
            if hasattr(product, key) and value is not None:
                setattr(product, key, value)

        await self.db.commit()
        return {
            "product_id": product.id,
            "name": product.name,
            "message": f"Товар '{product.name}' обновлён",
        }

    async def delete_product(self, product_id: int) -> dict[str, Any]:
        result = await self.db.execute(
            select(Product).where(Product.id == product_id)
        )
        product = result.scalar_one_or_none()
        if not product:
            return {"error": "Товар не найден"}

        name = product.name
        await self.db.delete(product)
        await self.db.commit()
        return {"message": f"Товар '{name}' удалён"}

    # ── Favorites ─────────────────────────────────────────────────

    async def get_favorites(self, user_id: int) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(Favorite)
            .where(Favorite.user_id == user_id)
            .options(selectinload(Favorite.product))
        )
        favorites = result.scalars().all()
        return [
            {
                "product_id": f.product_id,
                "product_name": f.product.name,
                "price": float(f.product.price),
            }
            for f in favorites
            if f.product
        ]

    async def add_to_favorites(
        self, user_id: int, product_id: int
    ) -> dict[str, Any]:
        try:
            product_id = int(product_id)
        except (TypeError, ValueError):
            return {"error": "Некорректный ID товара"}

        product = await self.db.execute(
            select(Product).where(Product.id == product_id)
        )
        product = product.scalar_one_or_none()
        if not product:
            return {"error": "Товар не найден"}

        existing = await self.db.execute(
            select(Favorite).where(
                Favorite.user_id == user_id,
                Favorite.product_id == product_id,
            )
        )
        if existing.scalar_one_or_none():
            return {"error": "Товар уже в избранном"}

        self.db.add(Favorite(user_id=user_id, product_id=product_id))
        await self.db.commit()
        return {
            "product_id": product_id,
            "product_name": product.name,
        }

    async def remove_from_favorites(
        self, user_id: int, product_id: int
    ) -> dict[str, Any]:
        try:
            product_id = int(product_id)
        except (TypeError, ValueError):
            return {"error": "Некорректный ID товара"}

        result = await self.db.execute(
            select(Favorite).where(
                Favorite.user_id == user_id,
                Favorite.product_id == product_id,
            )
        )
        fav = result.scalar_one_or_none()
        if not fav:
            return {"error": "Товар не в избранном"}

        await self.db.delete(fav)
        await self.db.commit()
        return {"product_id": product_id}

    # ── Helpers ──────────────────────────────────────────────────

    def _product_to_dict(
        self, p: Product, detailed: bool = False
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": p.id,
            "name": p.name,
            "price": float(p.price),
            "category": p.category,
            "color": p.color,
            "in_stock": p.in_stock,
        }

        if detailed:
            data.update({
                "description": p.description,
                "old_price": float(p.old_price) if p.old_price else None,
                "dimensions": p.dimensions,
                "materials": p.materials,
                "stock_quantity": p.stock_quantity,
                "rating": float(p.rating) if p.rating else None,
                "reviews_count": p.reviews_count,
            })
        else:
            desc = p.description or ""
            data["description"] = (
                desc[:200] + "..." if len(desc) > 200 else desc
            )

        return data
