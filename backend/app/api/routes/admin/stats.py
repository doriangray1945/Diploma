from datetime import datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.database import get_db
from app.models import Order, OrderItem, Product, User
from app.schemas.admin import (
    CategoryBreakdown,
    InventorySummary,
    LowStockProduct,
    RevenuePoint,
    StatsOverview,
    TopProduct,
)

router = APIRouter(dependencies=[Depends(require_admin)])


PERIOD_DAYS = {"7d": 7, "30d": 30}


def _period_start(period: str) -> datetime:
    days = PERIOD_DAYS.get(period, 7)
    return datetime.utcnow() - timedelta(days=days)


@router.get("/overview", response_model=StatsOverview)
async def overview(
    db: Annotated[AsyncSession, Depends(get_db)],
    period: Literal["7d", "30d"] = "7d",
):
    start = _period_start(period)
    end = datetime.utcnow()

    revenue_q = select(func.coalesce(func.sum(Order.total), 0)).where(
        Order.status != "cancelled",
        Order.created_at >= start,
    )
    count_q = select(func.count(Order.id)).where(
        Order.status != "cancelled",
        Order.created_at >= start,
    )
    users_q = select(func.count(User.id)).where(User.created_at >= start)

    revenue = float((await db.execute(revenue_q)).scalar_one() or 0)
    orders_count = int((await db.execute(count_q)).scalar_one())
    new_users = int((await db.execute(users_q)).scalar_one())
    aov = revenue / orders_count if orders_count else 0.0

    return StatsOverview(
        revenue=round(revenue, 2),
        orders_count=orders_count,
        aov=round(aov, 2),
        new_users=new_users,
        period_start=start,
        period_end=end,
    )


@router.get("/revenue-by-day", response_model=list[RevenuePoint])
async def revenue_by_day(
    db: Annotated[AsyncSession, Depends(get_db)],
    days: int = Query(30, ge=1, le=180),
):
    start = datetime.utcnow() - timedelta(days=days)
    day = func.date(Order.created_at)
    q = (
        select(day.label("d"), func.coalesce(func.sum(Order.total), 0).label("r"))
        .where(Order.status != "cancelled", Order.created_at >= start)
        .group_by(day)
        .order_by(day)
    )
    rows = (await db.execute(q)).all()
    by_day = {str(r.d): float(r.r or 0) for r in rows}

    out: list[RevenuePoint] = []
    for i in range(days):
        d = (start + timedelta(days=i)).date().isoformat()
        out.append(RevenuePoint(date=d, revenue=round(by_day.get(d, 0.0), 2)))
    return out


@router.get("/top-products", response_model=list[TopProduct])
async def top_products(
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(5, ge=1, le=20),
    days: int = Query(30, ge=1, le=365),
):
    start = datetime.utcnow() - timedelta(days=days)
    revenue_expr = func.sum(OrderItem.price * OrderItem.quantity).label("revenue")
    units_expr = func.sum(OrderItem.quantity).label("units")
    q = (
        select(
            Product.id,
            Product.name,
            Product.category,
            units_expr,
            revenue_expr,
        )
        .join(OrderItem, OrderItem.product_id == Product.id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.status != "cancelled", Order.created_at >= start)
        .group_by(Product.id, Product.name, Product.category)
        .order_by(revenue_expr.desc())
        .limit(limit)
    )
    rows = (await db.execute(q)).all()
    return [
        TopProduct(
            product_id=r.id,
            name=r.name,
            category=r.category,
            units=int(r.units or 0),
            revenue=round(float(r.revenue or 0), 2),
        )
        for r in rows
    ]


@router.get("/category-breakdown", response_model=list[CategoryBreakdown])
async def category_breakdown(
    db: Annotated[AsyncSession, Depends(get_db)],
    days: int = Query(30, ge=1, le=365),
):
    start = datetime.utcnow() - timedelta(days=days)
    revenue_expr = func.sum(OrderItem.price * OrderItem.quantity).label("revenue")
    units_expr = func.sum(OrderItem.quantity).label("units")
    q = (
        select(Product.category, units_expr, revenue_expr)
        .join(OrderItem, OrderItem.product_id == Product.id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.status != "cancelled", Order.created_at >= start)
        .group_by(Product.category)
        .order_by(revenue_expr.desc())
    )
    rows = (await db.execute(q)).all()
    return [
        CategoryBreakdown(
            category=r.category,
            revenue=round(float(r.revenue or 0), 2),
            units=int(r.units or 0),
        )
        for r in rows
    ]


@router.get("/low-stock", response_model=list[LowStockProduct])
async def low_stock(
    db: Annotated[AsyncSession, Depends(get_db)],
    threshold: int = Query(5, ge=0, le=1000),
):
    q = (
        select(Product)
        .where(and_(Product.stock_quantity < threshold, Product.in_stock == True))  # noqa: E712
        .order_by(Product.stock_quantity.asc())
    )
    rows = (await db.execute(q)).scalars().all()
    return [
        LowStockProduct(
            id=p.id, name=p.name, category=p.category,
            stock_quantity=p.stock_quantity, in_stock=p.in_stock,
        )
        for p in rows
    ]


@router.get("/inventory-summary", response_model=InventorySummary)
async def inventory_summary(
    db: Annotated[AsyncSession, Depends(get_db)],
    threshold: int = Query(5, ge=0, le=1000),
):
    total = int((await db.execute(select(func.count(Product.id)))).scalar_one())
    in_stock = int(
        (await db.execute(
            select(func.count(Product.id)).where(Product.in_stock == True)  # noqa: E712
        )).scalar_one()
    )
    low = int(
        (await db.execute(
            select(func.count(Product.id)).where(
                Product.in_stock == True,  # noqa: E712
                Product.stock_quantity < threshold,
            )
        )).scalar_one()
    )
    return InventorySummary(
        total_products=total,
        in_stock=in_stock,
        out_of_stock=total - in_stock,
        low_stock_count=low,
    )
