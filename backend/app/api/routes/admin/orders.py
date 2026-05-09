from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_admin
from app.core.database import get_db
from app.models import Order

router = APIRouter(dependencies=[Depends(require_admin)])


# Allowed status transitions. Final states have empty allowed sets.
TRANSITIONS: dict[str, set[str]] = {
    "pending":   {"confirmed", "cancelled"},
    "confirmed": {"shipping", "cancelled"},
    "shipping":  {"delivered"},
    "delivered": set(),
    "cancelled": set(),
}


Status = Literal["pending", "confirmed", "shipping", "delivered", "cancelled"]


class OrderItemView(BaseModel):
    id: int
    product_id: int | None = None
    product_name: str
    quantity: int
    price: float


class OrderView(BaseModel):
    id: int
    user_id: int
    user_email: str
    user_name: str
    status: str
    total: float
    address: str
    phone: str
    comment: str | None = None
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemView]
    allowed_transitions: list[str]


class StatusUpdate(BaseModel):
    status: Status


class OrderListView(BaseModel):
    items: list[OrderView]
    total: int


@router.get("", response_model=OrderListView)
async def list_orders(
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: Status | None = Query(None, alias="status"),
    user_id: int | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    q = (
        select(Order)
        .options(selectinload(Order.items), selectinload(Order.user))
        .order_by(desc(Order.created_at))
        .limit(limit)
    )
    if status_filter:
        q = q.where(Order.status == status_filter)
    if user_id is not None:
        q = q.where(Order.user_id == user_id)

    rows = (await db.execute(q)).scalars().all()
    items = [
        OrderView(
            id=o.id, user_id=o.user_id,
            user_email=o.user.email if o.user else "—",
            user_name=o.user.name if o.user else "—",
            status=o.status, total=float(o.total),
            address=o.address, phone=o.phone, comment=o.comment,
            created_at=o.created_at, updated_at=o.updated_at,
            items=[
                OrderItemView(
                    id=i.id, product_id=i.product_id, product_name=i.product_name,
                    quantity=i.quantity, price=float(i.price),
                )
                for i in o.items
            ],
            allowed_transitions=sorted(TRANSITIONS.get(o.status, set())),
        )
        for o in rows
    ]
    return OrderListView(items=items, total=len(items))


@router.patch("/{order_id}/status", response_model=OrderView)
async def update_status(
    order_id: int,
    body: StatusUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # Need items+variants eagerly so a cancel can return units to stock.
    order_q = (
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.items))
    )
    order = (await db.execute(order_q)).scalar_one_or_none()
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    allowed = TRANSITIONS.get(order.status, set())
    if body.status not in allowed:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Status transition '{order.status}' → '{body.status}' is not allowed",
        )

    # When cancelling a non-cancelled order, return reserved units to stock.
    # Stock was decremented at order creation (routes/orders.py:create_order),
    # so any state with stock-allocation must give it back on cancel.
    if body.status == "cancelled" and order.status != "cancelled":
        from app.models import ProductVariant
        for item in order.items:
            if item.variant_id is None:
                continue
            v = await db.get(ProductVariant, item.variant_id, with_for_update=True)
            if v is None:
                continue
            v.stock_quantity = (v.stock_quantity or 0) + item.quantity
            v.in_stock = v.stock_quantity > 0

    order.status = body.status
    await db.commit()
    await db.refresh(order)

    # Re-fetch with relations for response
    q = (
        select(Order)
        .options(selectinload(Order.items), selectinload(Order.user))
        .where(Order.id == order_id)
    )
    o = (await db.execute(q)).scalar_one()
    return OrderView(
        id=o.id, user_id=o.user_id,
        user_email=o.user.email if o.user else "—",
        user_name=o.user.name if o.user else "—",
        status=o.status, total=float(o.total),
        address=o.address, phone=o.phone, comment=o.comment,
        created_at=o.created_at, updated_at=o.updated_at,
        items=[
            OrderItemView(
                id=i.id, product_id=i.product_id, product_name=i.product_name,
                quantity=i.quantity, price=float(i.price),
            )
            for i in o.items
        ],
        allowed_transitions=sorted(TRANSITIONS.get(o.status, set())),
    )
