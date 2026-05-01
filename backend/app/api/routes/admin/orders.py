from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_admin
from app.core.database import get_db
from app.models import Order, OrderItem, User

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


@router.get("", response_model=list[OrderView])
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
    return [
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


@router.patch("/{order_id}/status", response_model=OrderView)
async def update_status(
    order_id: int,
    body: StatusUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    order = await db.get(Order, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    allowed = TRANSITIONS.get(order.status, set())
    if body.status not in allowed:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Status transition '{order.status}' → '{body.status}' is not allowed",
        )
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
