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
    """Create an order from the user's cart.

    Atomic: SELECT ... FOR UPDATE on each variant locks rows for the duration
    of the transaction, preventing concurrent buyers from oversubscribing
    stock. If any variant has insufficient stock, returns 409 with details
    and rolls back without touching cart or stock.
    """
    from app.models import ProductVariant
    cart_result = await db.execute(
        select(CartItem)
        .where(CartItem.user_id == current_user.id)
        .options(
            selectinload(CartItem.variant)
            .selectinload(ProductVariant.product)
        )
    )
    cart_items = list(cart_result.scalars().all())

    if not cart_items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    # Lock the variant rows for the transaction. Concurrent checkout of the
    # same SKU blocks here until our commit/rollback completes.
    # populate_existing=True forces ORM to refresh from this FOR UPDATE query
    # — without it, the variant cached by `selectinload(CartItem.variant)`
    # above (unlocked read) is returned and `v.stock_quantity` is stale.
    variant_ids = list({ci.variant_id for ci in cart_items})
    locked_result = await db.execute(
        select(ProductVariant)
        .where(ProductVariant.id.in_(variant_ids))
        .with_for_update()
        .options(selectinload(ProductVariant.product))
        .execution_options(populate_existing=True)
    )
    locked_variants = {v.id: v for v in locked_result.scalars().all()}

    # Reconcile cart against locked stock. Three states:
    # - sold_out      → variant is gone; user must remove (hard block)
    # - insufficient  → some left, but less than requested; recoverable if the
    #                   user explicitly accepts clamping via accept_clamping
    # - ok            → request fits stock entirely
    sold_out: list[dict] = []
    insufficient: list[dict] = []
    for ci in cart_items:
        v = locked_variants.get(ci.variant_id)
        if v is None or v.stock_quantity == 0:
            name = v.product.name if v and v.product else "(товар)"
            sold_out.append({
                "variant_id": ci.variant_id,
                "name": name,
                "color": v.color if v else None,
                "size_label": v.size_label if v else None,
                "reason": "sold_out",
                "available": 0,
                "requested": ci.quantity,
            })
        elif v.stock_quantity < ci.quantity:
            insufficient.append({
                "variant_id": v.id,
                "name": v.product.name if v.product else "(товар)",
                "color": v.color,
                "size_label": v.size_label,
                "reason": "insufficient",
                "available": v.stock_quantity,
                "requested": ci.quantity,
            })

    # Sold-out always blocks. Insufficient blocks unless user accepted clamping.
    if sold_out or (insufficient and not order_data.accept_clamping):
        await db.rollback()
        # `detail` is a dict (not the usual string) so the frontend can render
        # a modal with the specific unavailable SKUs and decide whether to
        # offer the «accept_clamping» retry based on `can_clamp`. A flat
        # string couldn't carry the per-item breakdown the UI needs.
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Корзина изменилась — некоторые товары недоступны",
                "items": sold_out + insufficient,
                "can_clamp": (not sold_out) and bool(insufficient),
            },
        )

    # Build order, decrement stock, clear cart. With accept_clamping=True,
    # insufficient items get qty = available; ok items use ci.quantity.
    total = 0.0
    order_items: list[OrderItem] = []
    for ci in cart_items:
        v = locked_variants[ci.variant_id]
        actual_qty = min(ci.quantity, v.stock_quantity)
        product = v.product
        item_total = float(v.price) * actual_qty
        total += item_total

        order_items.append(OrderItem(
            product_id=product.id,
            variant_id=v.id,
            product_name=product.name,
            quantity=actual_qty,
            price=float(v.price),
        ))

        v.stock_quantity = v.stock_quantity - actual_qty
        v.in_stock = v.stock_quantity > 0

    order = Order(
        user_id=current_user.id,
        status="pending",
        total=total,
        address=order_data.address,
        phone=order_data.phone,
        comment=order_data.comment,
    )
    db.add(order)
    await db.flush()

    for item in order_items:
        item.order_id = order.id
        db.add(item)

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
