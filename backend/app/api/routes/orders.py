from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models import Order, OrderItem, CartItem, User
from app.schemas import OrderCreate, OrderResponse, OrderListResponse, OrderItemResponse
from app.api.deps import get_current_user

router = APIRouter()


@router.get("", response_model=OrderListResponse)
async def get_orders(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    result = await db.execute(
        select(Order)
        .where(Order.user_id == current_user.id)
        .options(selectinload(Order.items))
        .order_by(Order.created_at.desc())
    )
    orders = result.scalars().all()

    items = []
    for order in orders:
        order_items = [
            OrderItemResponse(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product_name,
                quantity=item.quantity,
                price=float(item.price)
            )
            for item in order.items
        ]
        items.append(OrderResponse(
            id=order.id,
            status=order.status,
            total=float(order.total),
            address=order.address,
            phone=order.phone,
            comment=order.comment,
            created_at=order.created_at,
            updated_at=order.updated_at,
            items=order_items
        ))

    return OrderListResponse(items=items, total=len(items))


@router.post("", response_model=OrderResponse)
async def create_order(
    order_data: OrderCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    # Get cart items
    cart_result = await db.execute(
        select(CartItem)
        .where(CartItem.user_id == current_user.id)
        .options(selectinload(CartItem.product))
    )
    cart_items = cart_result.scalars().all()

    if not cart_items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    # Calculate total and create order items
    total = 0.0
    order_items = []
    for cart_item in cart_items:
        product = cart_item.product
        item_total = float(product.price) * cart_item.quantity
        total += item_total

        order_items.append(OrderItem(
            product_id=product.id,
            product_name=product.name,
            quantity=cart_item.quantity,
            price=float(product.price)
        ))

    # Create order
    order = Order(
        user_id=current_user.id,
        status="pending",
        total=total,
        address=order_data.address,
        phone=order_data.phone,
        comment=order_data.comment
    )
    db.add(order)
    await db.flush()

    # Add order items
    for item in order_items:
        item.order_id = order.id
        db.add(item)

    # Clear cart
    for cart_item in cart_items:
        await db.delete(cart_item)

    await db.commit()
    await db.refresh(order)

    # Reload with items
    result = await db.execute(
        select(Order)
        .where(Order.id == order.id)
        .options(selectinload(Order.items))
    )
    order = result.scalar_one()

    return OrderResponse(
        id=order.id,
        status=order.status,
        total=float(order.total),
        address=order.address,
        phone=order.phone,
        comment=order.comment,
        created_at=order.created_at,
        updated_at=order.updated_at,
        items=[
            OrderItemResponse(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product_name,
                quantity=item.quantity,
                price=float(item.price)
            )
            for item in order.items
        ]
    )


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    result = await db.execute(
        select(Order)
        .where(Order.id == order_id, Order.user_id == current_user.id)
        .options(selectinload(Order.items))
    )
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    return OrderResponse(
        id=order.id,
        status=order.status,
        total=float(order.total),
        address=order.address,
        phone=order.phone,
        comment=order.comment,
        created_at=order.created_at,
        updated_at=order.updated_at,
        items=[
            OrderItemResponse(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product_name,
                quantity=item.quantity,
                price=float(item.price)
            )
            for item in order.items
        ]
    )
