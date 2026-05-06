from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.semantic_config import MATERIAL_GROUPS, resolve_material
from app.models import Product, CartItem, Order, OrderItem, Favorite
from app.services.products import apply_search_filter


def _row_matches(product: Any, flt: dict[str, Any]) -> bool:
    """True if `product` matches every non-empty key in the filter.

    Used by remove_*_by_filter. AND across keys; OR within array values.
    """
    if product is None:
        return False
    if flt.get("category") and product.category != flt["category"]:
        return False

    color = flt.get("color")
    if color:
        color_list = color if isinstance(color, list) else [color]
        if product.color not in color_list:
            return False

    material = flt.get("material")
    if material:
        material_list = material if isinstance(material, list) else [material]
        all_substrings: list[str] = []
        for m in material_list:
            all_substrings.extend(MATERIAL_GROUPS.get(m, []))
        materials_str = (product.materials or "").lower()
        if all_substrings and not any(s.lower() in materials_str for s in all_substrings):
            return False

    if flt.get("product_name"):
        needle = flt["product_name"].lower()
        if needle not in (product.name or "").lower():
            return False
    return True


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
        # Build base query with non-search filters first, then layer BM25
        # full-text search on top via apply_search_filter. Same code path
        # as /api/products — keeps UI search box and AI chat consistent.
        base = select(Product)
        if category:
            base = base.where(Product.category.ilike(f"%{category}%"))
        if min_price is not None:
            base = base.where(Product.price >= min_price)
        if max_price is not None:
            base = base.where(Product.price <= max_price)
        if in_stock:
            base = base.where(Product.in_stock == True)  # noqa: E712

        # Color filter — list (multi-value) OR single string.
        # Multiple values OR'd: «красные или синие диваны».
        color = filters.get("color")
        if color:
            color_list = color if isinstance(color, list) else [color]
            base = base.where(or_(*[
                Product.color.ilike(f"%{c}%") for c in color_list if c
            ]))

        # Material filter — list of coarse-grained labels («твёрдое» =
        # ['дерево', 'металл']). Each label expands via MATERIAL_GROUPS
        # to its catalog substrings, all ORd into a single big WHERE.
        material = filters.get("material")
        if material:
            material_list = material if isinstance(material, list) else [material]
            all_substrings: list[str] = []
            for m in material_list:
                all_substrings.extend(resolve_material(m))
            if all_substrings:
                base = base.where(or_(*[
                    Product.materials.ilike(f"%{s}%") for s in all_substrings
                ]))

        searchable = apply_search_filter(base, query).limit(limit)
        result = await self.db.execute(searchable)
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

    async def clear_cart(self, user_id: int) -> dict[str, Any]:
        result = await self.db.execute(
            select(CartItem).where(CartItem.user_id == user_id)
        )
        items = result.scalars().all()
        for item in items:
            await self.db.delete(item)
        await self.db.commit()
        return {"cleared": True, "removed_count": len(items)}

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

    # ── Bulk admin ops (chat tools update_stock/update_prices/get_sales_analytics)

    async def bulk_update_stock(
        self, filter: dict[str, Any], operation: str, quantity: int
    ) -> dict[str, Any]:
        from app.schemas.admin import AdminFilter
        from app.services.products import bulk_update_stock as svc

        try:
            flt = AdminFilter(**(filter or {}))
        except Exception as e:
            return {"error": f"Invalid filter: {e}"}
        affected = await svc(self.db, flt, operation, quantity)
        return {
            "affected_count": affected,
            "operation": operation,
            "message": f"Обновлены остатки {affected} товаров (операция: {operation}, количество: {quantity})",
        }

    async def bulk_update_prices(
        self, filter: dict[str, Any], operation: str, value: int
    ) -> dict[str, Any]:
        from app.schemas.admin import AdminFilter
        from app.services.products import bulk_update_prices as svc

        try:
            flt = AdminFilter(**(filter or {}))
        except Exception as e:
            return {"error": f"Invalid filter: {e}"}
        affected, delta = await svc(self.db, flt, operation, value)
        return {
            "affected_count": affected,
            "operation": operation,
            "revenue_impact": float(delta),
            "message": f"Обновлены цены {affected} товаров (операция: {operation}, значение: {value})",
        }

    async def query_sales_analytics(self, **kwargs: Any) -> dict[str, Any]:
        from app.schemas.admin import AdminFilter, AnalyticsQuery
        from app.services import analytics

        # Filter pre-parse: tool may pass dict, schema needs AdminFilter
        if "filter" in kwargs and isinstance(kwargs["filter"], dict):
            try:
                kwargs["filter"] = AdminFilter(**kwargs["filter"])
            except Exception as e:
                return {"error": f"Invalid filter: {e}"}
        try:
            payload = AnalyticsQuery(**kwargs)
        except Exception as e:
            return {"error": f"Invalid analytics query: {e}"}
        buckets = await analytics.query(
            self.db,
            period=payload.period,
            group_by=payload.group_by,
            metric=payload.metric,
            sort=payload.sort,
            limit=payload.limit,
            from_date=payload.from_date,
            to_date=payload.to_date,
            filter=payload.filter,
        )
        return {
            "buckets": [b.model_dump() for b in buckets],
            "metric": payload.metric,
            "group_by": payload.group_by,
            "period": payload.period,
        }

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

    async def clear_favorites(self, user_id: int) -> dict[str, Any]:
        result = await self.db.execute(
            select(Favorite).where(Favorite.user_id == user_id)
        )
        items = result.scalars().all()
        for item in items:
            await self.db.delete(item)
        await self.db.commit()
        return {"cleared": True, "removed_count": len(items)}

    async def remove_favorites_by_filter(
        self, user_id: int, flt: dict[str, Any]
    ) -> dict[str, Any]:
        """Remove favorites matching `flt` against the user's current list.

        flt keys: category, color, material, product_name, all.
        Returns {removed: [{product_id, product_name}, ...], count: N}.
        """
        return await self._remove_by_filter(user_id, flt, table="favorites")

    async def remove_cart_by_filter(
        self, user_id: int, flt: dict[str, Any]
    ) -> dict[str, Any]:
        """Symmetric to remove_favorites_by_filter, for cart_items."""
        return await self._remove_by_filter(user_id, flt, table="cart")

    async def _remove_by_filter(
        self, user_id: int, flt: dict[str, Any], table: str
    ) -> dict[str, Any]:
        Model = Favorite if table == "favorites" else CartItem
        # Pull the user's full set joined with Product so we can apply
        # the agent-emitted filter against product attributes (category,
        # color, materials substring) directly in Python — small set
        # (<200 items realistic) so no SQL JOIN headache needed.
        rows = (await self.db.execute(
            select(Model).where(Model.user_id == user_id)
            .options(selectinload(Model.product))
        )).scalars().all()

        if flt.get("all"):
            matching = list(rows)
        else:
            matching = [r for r in rows if _row_matches(r.product, flt)]

        removed = []
        for row in matching:
            removed.append({
                "product_id": row.product_id,
                "product_name": row.product.name if row.product else None,
            })
            await self.db.delete(row)
        await self.db.commit()
        return {"removed": removed, "count": len(removed)}

    # ── Filter discovery ────────────────────────────────────────

    _filter_cache: dict[str, Any] | None = None
    _filter_cache_ts: float = 0.0

    async def get_filter_options(self) -> dict[str, Any]:
        """Return available filter values from DB (cached for 60s)."""
        import time
        from sqlalchemy import func

        now = time.time()
        if self._filter_cache and (now - self._filter_cache_ts) < 60:
            return self._filter_cache

        cat_result = await self.db.execute(
            select(Product.category).distinct()
        )
        categories = sorted([r for r in cat_result.scalars().all() if r])

        color_result = await self.db.execute(
            select(Product.color).distinct().where(Product.color.isnot(None))
        )
        colors = sorted([r for r in color_result.scalars().all() if r])

        # Materials: surface canonical groups (MATERIAL_GROUPS keys), not raw
        # DB tokens. Frontend filter and LLM-prompt enum stay aligned; backend
        # expands group → substrings via resolve_material() during search.
        materials = list(MATERIAL_GROUPS.keys())

        price_result = await self.db.execute(
            select(func.min(Product.price), func.max(Product.price))
        )
        row = price_result.one()
        min_p, max_p = float(row[0] or 0), float(row[1] or 0)

        self._filter_cache = {
            "categories": categories,
            "colors": colors,
            "materials": materials,
            "price_range": {"min": min_p, "max": max_p},
        }
        self._filter_cache_ts = now
        return self._filter_cache

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
