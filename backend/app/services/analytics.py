"""Flexible sales analytics — single endpoint replaces overview/top-products/etc.

Builds dynamic SQL aggregating Order/OrderItem joined with ProductVariant
and Product:
- period: today/week/month/quarter/year/custom — sets time window
- group_by: product/category/color/material/price_level/day — GROUP BY dimension
- metric: revenue/units_sold/orders_count/avg_check — what to aggregate
- sort/limit — output ranking
- filter: AdminFilter — restrict to subset of catalog (matches variant-set)
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Order, OrderItem, Product, ProductVariant
from app.schemas.admin import AdminFilter, AnalyticsBucket
from app.services.products import _apply_admin_filter


_PERIOD_DAYS = {"today": 1, "week": 7, "month": 30, "quarter": 90, "year": 365}


def _period_window(
    period: str,
    from_date: date | None = None,
    to_date: date | None = None,
) -> tuple[datetime, datetime]:
    if period == "custom":
        assert from_date and to_date
        return (
            datetime.combine(from_date, datetime.min.time()),
            datetime.combine(to_date, datetime.max.time()),
        )
    days = _PERIOD_DAYS.get(period, 7)
    end = datetime.utcnow()
    start = end - timedelta(days=days)
    return (start, end)


def _group_expr(group_by: str):
    """Pick the GROUP BY expression. After variant migration:
    - color / price_level live on ProductVariant
    - material stays on Product
    - product / category stay on Product
    - day operates on Order.created_at
    """
    if group_by == "product":
        return Product.name
    if group_by == "category":
        return Product.category
    if group_by == "color":
        return ProductVariant.color
    if group_by == "material":
        return Product.materials
    if group_by == "price_level":
        return case(
            (ProductVariant.price < 30000, "budget"),
            (ProductVariant.price < 80000, "mid"),
            else_="premium",
        )
    if group_by == "day":
        return func.date(Order.created_at)
    raise ValueError(f"unknown group_by: {group_by}")


def _metric_expr(metric: str):
    if metric == "revenue":
        return func.coalesce(func.sum(OrderItem.price * OrderItem.quantity), 0)
    if metric == "units_sold":
        return func.coalesce(func.sum(OrderItem.quantity), 0)
    if metric == "orders_count":
        return func.count(func.distinct(Order.id))
    if metric == "avg_check":
        return func.coalesce(func.avg(Order.total), 0)
    raise ValueError(f"unknown metric: {metric}")


async def query(
    db: AsyncSession,
    *,
    period: str,
    group_by: str,
    metric: str,
    sort: str = "desc",
    limit: int = 10,
    from_date: date | None = None,
    to_date: date | None = None,
    filter: AdminFilter | None = None,
) -> list[AnalyticsBucket]:
    start, end = _period_window(period, from_date, to_date)
    grp = _group_expr(group_by)
    val = _metric_expr(metric)
    units = func.coalesce(func.sum(OrderItem.quantity), 0).label("units")

    # Base JOIN chain: OrderItem → ProductVariant → Product (via OrderItem.variant_id).
    # If OrderItem.variant_id is NULL (legacy data) the row drops out — fine for
    # variant-grouped queries. For product/category we could fall back via
    # OrderItem.product_id, but the variant column is the source of truth.
    q = (
        select(grp.label("key"), val.label("value"), units)
        .select_from(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .join(ProductVariant, ProductVariant.id == OrderItem.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(Order.status != "cancelled", Order.created_at.between(start, end))
        .group_by(grp)
    )

    if filter is not None:
        # Apply catalog filters by intersecting with matching variant subset.
        filtered_ids = (await db.execute(
            _apply_admin_filter(select(ProductVariant.id), filter)
        )).scalars().all()
        if not filtered_ids:
            return []
        q = q.where(ProductVariant.id.in_(filtered_ids))

    if sort == "desc":
        q = q.order_by(val.desc())
    else:
        q = q.order_by(val.asc())
    q = q.limit(limit)

    rows = (await db.execute(q)).all()
    return [
        AnalyticsBucket(
            key=str(r.key) if r.key is not None else "—",
            value=round(float(r.value or 0), 2),
            units=int(r.units or 0),
        )
        for r in rows
    ]
