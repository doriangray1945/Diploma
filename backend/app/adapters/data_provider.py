"""Data provider used by core LLM chat tools. Variant-aware: tools still
emit `product_id` (the model knows products, not SKU IDs), and we resolve
to default_variant for cart/favorites mutations. Filter queries scan
variant fields for price/color/stock since those moved off Product.
"""
import logging
from typing import Any

from sqlalchemy import or_, select, exists
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.services.semantics import MATERIAL_GROUPS, resolve_material, resolve_price_level
from app.models import Product, ProductVariant, CartItem, Order, OrderItem, Favorite
from app.services.products import apply_search_filter


log = logging.getLogger(__name__)


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
        # Match any variant of the product against the color list.
        product_colors = {v.color for v in (product.variants or []) if v.color}
        if not (set(color_list) & product_colors):
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
        # Build base on Product, push price/color/in_stock filters into
        # EXISTS subqueries against ProductVariant — a product passes if at
        # least one of its variants matches.
        base = select(Product).options(selectinload(Product.variants))
        if category:
            base = base.where(Product.category.ilike(f"%{category}%"))

        variant_filters: list = []
        if min_price is not None:
            variant_filters.append(ProductVariant.price >= min_price)
        if max_price is not None:
            variant_filters.append(ProductVariant.price <= max_price)
        if in_stock:
            variant_filters.append(ProductVariant.in_stock == True)  # noqa: E712

        color = filters.get("color")
        if color:
            color_list = color if isinstance(color, list) else [color]
            variant_filters.append(or_(*[
                ProductVariant.color.ilike(f"%{c}%") for c in color_list if c
            ]))

        if variant_filters:
            base = base.where(exists().where(
                ProductVariant.product_id == Product.id, *variant_filters
            ))

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
                select(Product)
                .where(Product.id == product_id)
                .options(selectinload(Product.variants))
            )
            product = result.scalar_one_or_none()
        except Exception as e:
            log.warning("get_product(%d) failed: %r", product_id, e)
            await self.db.rollback()
            return None
        if not product:
            return None
        return self._product_to_dict(product, detailed=True)

    async def _resolve_variant_id(
        self, product_id: int, variant_filter: dict[str, Any] | None = None
    ) -> int | None:
        """Tools pass product_id; we map to a concrete variant.

        Without `variant_filter`: return product's default variant (or first).

        With `variant_filter` (any of color/material/price_level): find the
        first variant of this product matching the filter. ORDER BY
        is_default DESC, id ASC, LIMIT 1. Returns None when nothing matches —
        caller treats that as «product skipped, no SKU under that filter».
        """
        if not variant_filter:
            result = await self.db.execute(
                select(Product.default_variant_id).where(Product.id == product_id)
            )
            vid = result.scalar_one_or_none()
            if vid:
                return vid
            first = await self.db.execute(
                select(ProductVariant.id)
                .where(ProductVariant.product_id == product_id)
                .order_by(ProductVariant.id)
                .limit(1)
            )
            return first.scalar_one_or_none()

        q = select(ProductVariant.id).where(ProductVariant.product_id == product_id)

        colors = variant_filter.get("color")
        if colors:
            color_list = colors if isinstance(colors, list) else [colors]
            q = q.where(ProductVariant.color.in_(color_list))

        price_level = variant_filter.get("price_level")
        if price_level:
            lvl_min, lvl_max = resolve_price_level(price_level)
            if lvl_min is not None:
                q = q.where(ProductVariant.price >= lvl_min)
            if lvl_max is not None:
                q = q.where(ProductVariant.price <= lvl_max)

        materials = variant_filter.get("material")
        if materials:
            material_list = materials if isinstance(materials, list) else [materials]
            substrings: list[str] = []
            for m in material_list:
                substrings.extend(resolve_material(m) or [m])
            if substrings:
                q = q.join(Product, Product.id == ProductVariant.product_id).where(
                    or_(*[Product.materials.ilike(f"%{s}%") for s in substrings])
                )

        q = q.order_by(ProductVariant.is_default.desc(), ProductVariant.id.asc()).limit(1)
        return (await self.db.execute(q)).scalar_one_or_none()

    # ── Cart ─────────────────────────────────────────────────────

    async def add_to_cart(
        self,
        user_id: int,
        product_id: int,
        quantity: int = 1,
        variant_filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            product_id = int(product_id)
            quantity = int(quantity)
        except (TypeError, ValueError):
            return {"error": "Некорректные параметры"}

        product_result = await self.db.execute(
            select(Product)
            .where(Product.id == product_id)
            .options(selectinload(Product.variants))
        )
        product = product_result.scalar_one_or_none()
        if not product:
            return {"error": "Товар не найден"}

        variant_id = await self._resolve_variant_id(product_id, variant_filter)
        if not variant_id:
            if variant_filter:
                return {"error": "Нет вариантов товара под заданный фильтр"}
            return {"error": "Нет доступных вариантов товара"}

        variant = next((v for v in product.variants if v.id == variant_id), None)
        if variant and not variant.in_stock:
            return {"error": "Товар не в наличии"}

        cart_result = await self.db.execute(
            select(CartItem).where(
                CartItem.user_id == user_id,
                CartItem.variant_id == variant_id,
            )
        )
        existing = cart_result.scalar_one_or_none()
        existing_qty = existing.quantity if existing else 0

        # Stock validation — same rule as REST cart route.
        stock = variant.stock_quantity if variant else 0
        if existing_qty + quantity > stock:
            available = max(0, stock - existing_qty)
            if existing_qty == 0:
                msg = f"На складе осталось {stock} шт."
            else:
                msg = (
                    f"На складе осталось {stock} шт., в корзине уже {existing_qty} — "
                    f"можно добавить ещё {available}"
                )
            return {"error": msg}

        if existing:
            existing.quantity += quantity
        else:
            self.db.add(
                CartItem(
                    user_id=user_id,
                    variant_id=variant_id,
                    quantity=quantity,
                )
            )
        await self.db.commit()

        return {
            "product_id": product_id,
            "variant_id": variant_id,
            "product_name": product.name,
            "quantity": quantity,
            "price": float(variant.price) if variant else 0.0,
        }

    async def get_cart(self, user_id: int) -> dict[str, Any]:
        result = await self.db.execute(
            select(CartItem)
            .where(CartItem.user_id == user_id)
            .options(
                selectinload(CartItem.variant)
                .selectinload(ProductVariant.product)
            )
        )
        items = result.scalars().all()

        total = 0.0
        cart_items = []
        for item in items:
            variant = item.variant
            if not variant:
                continue
            product = variant.product
            subtotal = float(variant.price) * item.quantity
            total += subtotal
            cart_items.append({
                "id": item.id,
                "product_id": product.id if product else None,
                "variant_id": variant.id,
                "product_name": product.name if product else "",
                "color": variant.color,
                "size_label": variant.size_label,
                "quantity": item.quantity,
                "price": float(variant.price),
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
            .options(
                selectinload(CartItem.variant)
                .selectinload(ProductVariant.product)
            )
        )
        cart_items = list(cart_result.scalars().all())

        if not cart_items:
            return {"error": "Корзина пуста"}

        # Lock variants for the transaction.
        variant_ids = list({ci.variant_id for ci in cart_items})
        locked = (await self.db.execute(
            select(ProductVariant)
            .where(ProductVariant.id.in_(variant_ids))
            .with_for_update()
            .options(selectinload(ProductVariant.product))
        )).scalars().all()
        by_id = {v.id: v for v in locked}

        # Fail loudly: any sold-out / insufficient → no order created.
        unavailable: list[str] = []
        for ci in cart_items:
            v = by_id.get(ci.variant_id)
            if v is None or v.stock_quantity == 0:
                name = v.product.name if v and v.product else f"товар #{ci.variant_id}"
                unavailable.append(f"«{name}» распродан")
            elif v.stock_quantity < ci.quantity:
                name = v.product.name if v.product else f"товар #{v.id}"
                unavailable.append(
                    f"«{name}»: запрошено {ci.quantity}, осталось {v.stock_quantity}"
                )
        if unavailable:
            await self.db.rollback()
            return {
                "error": (
                    "Корзина изменилась: " + "; ".join(unavailable) +
                    ". Удалите недоступные товары или измените количество."
                )
            }

        total = 0.0
        order_items = []
        for ci in cart_items:
            v = by_id[ci.variant_id]
            product = v.product
            item_total = float(v.price) * ci.quantity
            total += item_total
            order_items.append(
                OrderItem(
                    product_id=product.id if product else None,
                    variant_id=v.id,
                    product_name=product.name if product else "",
                    quantity=ci.quantity,
                    price=float(v.price),
                )
            )
            v.stock_quantity = v.stock_quantity - ci.quantity
            v.in_stock = v.stock_quantity > 0

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

    # ── Admin bulk ops (chat tools update_stock/update_prices/get_sales_analytics) ──

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
            "message": (
                f"Обновлены остатки {affected} вариантов "
                f"(операция: {operation}, количество: {quantity})"
            ),
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
            "message": (
                f"Обновлены цены {affected} вариантов "
                f"(операция: {operation}, значение: {value})"
            ),
        }

    async def query_sales_analytics(self, **kwargs: Any) -> dict[str, Any]:
        from app.schemas.admin import AdminFilter, AnalyticsQuery
        from app.services import analytics

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
            .options(
                selectinload(Favorite.variant)
                .selectinload(ProductVariant.product)
            )
        )
        favorites = result.scalars().all()
        out = []
        for f in favorites:
            v = f.variant
            if not v:
                continue
            product = v.product
            out.append({
                "product_id": product.id if product else None,
                "variant_id": v.id,
                "product_name": product.name if product else "",
                "color": v.color,
                "price": float(v.price),
            })
        return out

    async def add_to_favorites(
        self,
        user_id: int,
        product_id: int,
        variant_filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            product_id = int(product_id)
        except (TypeError, ValueError):
            return {"error": "Некорректный ID товара"}

        product_result = await self.db.execute(
            select(Product).where(Product.id == product_id)
        )
        product = product_result.scalar_one_or_none()
        if not product:
            return {"error": "Товар не найден"}

        variant_id = await self._resolve_variant_id(product_id, variant_filter)
        if not variant_id:
            if variant_filter:
                return {"error": "Нет вариантов товара под заданный фильтр"}
            return {"error": "Нет доступных вариантов товара"}

        existing = await self.db.execute(
            select(Favorite).where(
                Favorite.user_id == user_id,
                Favorite.variant_id == variant_id,
            )
        )
        if existing.scalar_one_or_none():
            return {"error": "Товар уже в избранном"}

        self.db.add(Favorite(user_id=user_id, variant_id=variant_id))
        await self.db.commit()
        return {
            "product_id": product_id,
            "variant_id": variant_id,
            "product_name": product.name,
        }

    async def remove_from_favorites(
        self, user_id: int, product_id: int
    ) -> dict[str, Any]:
        try:
            product_id = int(product_id)
        except (TypeError, ValueError):
            return {"error": "Некорректный ID товара"}

        # Remove ALL variants of this product from user's favorites (LLM thinks product-level).
        rows = (await self.db.execute(
            select(Favorite)
            .join(ProductVariant, Favorite.variant_id == ProductVariant.id)
            .where(
                Favorite.user_id == user_id,
                ProductVariant.product_id == product_id,
            )
        )).scalars().all()
        if not rows:
            return {"error": "Товар не в избранном"}
        for r in rows:
            await self.db.delete(r)
        await self.db.commit()
        return {"product_id": product_id, "removed_count": len(rows)}

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
        return await self._remove_by_filter(user_id, flt, table="favorites")

    async def remove_cart_by_filter(
        self, user_id: int, flt: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._remove_by_filter(user_id, flt, table="cart")

    async def _remove_by_filter(
        self, user_id: int, flt: dict[str, Any], table: str
    ) -> dict[str, Any]:
        Model = Favorite if table == "favorites" else CartItem
        rows = (await self.db.execute(
            select(Model)
            .where(Model.user_id == user_id)
            .options(
                selectinload(Model.variant)
                .selectinload(ProductVariant.product)
                .selectinload(Product.variants)
            )
        )).scalars().all()

        if flt.get("all"):
            matching = list(rows)
        else:
            matching = [
                r for r in rows
                if r.variant and _row_matches(r.variant.product, flt)
            ]

        removed = []
        for row in matching:
            product = row.variant.product if row.variant else None
            removed.append({
                "product_id": product.id if product else None,
                "variant_id": row.variant_id,
                "product_name": product.name if product else None,
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

        # Colors and prices live on variants now.
        color_result = await self.db.execute(
            select(ProductVariant.color)
            .distinct()
            .where(ProductVariant.color.isnot(None))
        )
        colors = sorted([r for r in color_result.scalars().all() if r])

        materials = list(MATERIAL_GROUPS.keys())

        price_result = await self.db.execute(
            select(func.min(ProductVariant.price), func.max(ProductVariant.price))
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
        # Pick default variant for snapshot price/color/stock.
        variants = list(p.variants or [])
        default = next((v for v in variants if v.is_default), variants[0] if variants else None)

        data: dict[str, Any] = {
            "id": p.id,
            "name": p.name,
            "category": p.category,
            "price": float(default.price) if default else 0.0,
            "color": default.color if default else None,
            "in_stock": bool(default.in_stock) if default else False,
        }

        if detailed:
            data.update({
                "description": p.description,
                "old_price": float(default.old_price) if default and default.old_price else None,
                "dimensions": p.dimensions,
                "materials": p.materials,
                "stock_quantity": default.stock_quantity if default else 0,
                "rating": float(p.rating) if p.rating else None,
                "reviews_count": p.reviews_count,
                "variants": [
                    {"id": v.id, "color": v.color, "size_label": v.size_label,
                     "price": float(v.price), "stock_quantity": v.stock_quantity,
                     "in_stock": v.in_stock}
                    for v in variants
                ],
            })
        else:
            desc = p.description or ""
            data["description"] = (
                desc[:200] + "..." if len(desc) > 200 else desc
            )

        return data
