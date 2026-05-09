"""Cart endpoints — variant-aware. Cart items reference a specific
ProductVariant SKU; the product is reached via variant.product.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models import CartItem, Product, ProductVariant, User, Favorite
from app.schemas import CartItemCreate, CartItemUpdate, CartResponse, CartItemResponse, ProductResponse
from app.schemas.product import ProductVariantResponse
from app.api.deps import get_current_user
from app.api.routes.products import _serialize_product

router = APIRouter()


def _serialize_cart_item(
    item: CartItem,
    favorite_variant_ids: set[int],
) -> CartItemResponse:
    variant = item.variant
    product = variant.product
    stock = variant.stock_quantity or 0
    raw_qty = item.quantity
    out_of_stock = stock == 0
    # When fully sold out, surface the original cart qty so the UI can show
    # "вы хотели N шт" alongside the «Нет в наличии» badge — no clamp here.
    # When 0 < stock < raw_qty (admin lowered), clamp and mark as adjusted.
    if out_of_stock:
        displayed_qty = raw_qty
        adjusted = False
    else:
        displayed_qty = min(raw_qty, stock)
        adjusted = displayed_qty != raw_qty
    return CartItemResponse(
        id=item.id,
        variant_id=item.variant_id,
        product_id=product.id,
        quantity=displayed_qty,
        product=_serialize_product(product, favorite_variant_ids),
        selected_color=variant.color,
        selected_size=variant.size_label,
        selected_price=float(variant.price),
        selected_images=variant.images or [],
        selected_stock=stock,
        adjusted=adjusted,
        out_of_stock=out_of_stock,
        created_at=item.created_at,
    )


async def _load_cart_items(db: AsyncSession, user_id: int) -> list[CartItem]:
    result = await db.execute(
        select(CartItem)
        .where(CartItem.user_id == user_id)
        .options(
            selectinload(CartItem.variant)
            .selectinload(ProductVariant.product)
            .selectinload(Product.variants)
        )
    )
    return list(result.scalars().all())


async def _user_favorite_variant_ids(db: AsyncSession, user_id: int) -> set[int]:
    fav_result = await db.execute(
        select(Favorite.variant_id).where(Favorite.user_id == user_id)
    )
    return set(fav_result.scalars().all())


@router.get("", response_model=CartResponse)
async def get_cart(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    cart_items = await _load_cart_items(db, current_user.id)
    fav_ids = await _user_favorite_variant_ids(db, current_user.id)

    items = []
    total = 0.0
    for item in cart_items:
        serialized = _serialize_cart_item(item, fav_ids)
        items.append(serialized)
        # Sold-out items don't contribute to total — checkout would refuse
        # them anyway. Use serialized.quantity so adjusted clamps are honoured.
        if not serialized.out_of_stock:
            total += serialized.selected_price * serialized.quantity

    return CartResponse(
        items=items,
        total=round(total, 2),
        items_count=len(items),
    )


@router.post("/items", response_model=CartItemResponse)
async def add_to_cart(
    item_data: CartItemCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    variant = (await db.execute(
        select(ProductVariant)
        .where(ProductVariant.id == item_data.variant_id)
        .options(selectinload(ProductVariant.product).selectinload(Product.variants))
    )).scalar_one_or_none()
    if not variant:
        raise HTTPException(status_code=404, detail="Product variant not found")

    existing = (await db.execute(
        select(CartItem).where(
            CartItem.user_id == current_user.id,
            CartItem.variant_id == item_data.variant_id,
        )
    )).scalar_one_or_none()
    existing_qty = existing.quantity if existing else 0

    # Stock validation: total in cart after this op must not exceed stock_quantity.
    if existing_qty + item_data.quantity > variant.stock_quantity:
        available = max(0, variant.stock_quantity - existing_qty)
        if existing_qty == 0:
            detail = f"На складе осталось {variant.stock_quantity} шт."
        else:
            detail = (
                f"На складе осталось {variant.stock_quantity} шт., "
                f"в корзине уже {existing_qty} — можно добавить ещё {available}"
            )
        raise HTTPException(status_code=400, detail=detail)

    if existing:
        existing.quantity += item_data.quantity
        await db.commit()
        await db.refresh(existing)
        cart_item = existing
    else:
        cart_item = CartItem(
            user_id=current_user.id,
            variant_id=item_data.variant_id,
            quantity=item_data.quantity,
        )
        db.add(cart_item)
        await db.commit()
        await db.refresh(cart_item)

    # Re-load with eager-loaded relationships for serialization.
    cart_item = (await db.execute(
        select(CartItem)
        .where(CartItem.id == cart_item.id)
        .options(
            selectinload(CartItem.variant)
            .selectinload(ProductVariant.product)
            .selectinload(Product.variants)
        )
    )).scalar_one()

    fav_ids = await _user_favorite_variant_ids(db, current_user.id)
    return _serialize_cart_item(cart_item, fav_ids)


@router.put("/items/{item_id}", response_model=CartItemResponse)
async def update_cart_item(
    item_id: int,
    item_data: CartItemUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    result = await db.execute(
        select(CartItem)
        .where(CartItem.id == item_id, CartItem.user_id == current_user.id)
        .options(
            selectinload(CartItem.variant)
            .selectinload(ProductVariant.product)
            .selectinload(Product.variants)
        )
    )
    cart_item = result.scalar_one_or_none()

    if not cart_item:
        raise HTTPException(status_code=404, detail="Cart item not found")

    if item_data.quantity <= 0:
        await db.delete(cart_item)
        await db.commit()
        raise HTTPException(status_code=204, detail="Item removed from cart")

    # Stock validation: requested qty must fit current variant stock.
    variant = cart_item.variant
    if variant and item_data.quantity > variant.stock_quantity:
        raise HTTPException(
            status_code=400,
            detail=f"На складе осталось {variant.stock_quantity} шт.",
        )

    cart_item.quantity = item_data.quantity
    await db.commit()
    await db.refresh(cart_item)

    fav_ids = await _user_favorite_variant_ids(db, current_user.id)
    return _serialize_cart_item(cart_item, fav_ids)


@router.delete("/items/{item_id}")
async def remove_from_cart(
    item_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    result = await db.execute(
        select(CartItem).where(
            CartItem.id == item_id,
            CartItem.user_id == current_user.id
        )
    )
    cart_item = result.scalar_one_or_none()

    if not cart_item:
        raise HTTPException(status_code=404, detail="Cart item not found")

    await db.delete(cart_item)
    await db.commit()

    return {"message": "Item removed from cart"}


@router.delete("")
async def clear_cart(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    result = await db.execute(
        select(CartItem).where(CartItem.user_id == current_user.id)
    )
    cart_items = result.scalars().all()

    for item in cart_items:
        await db.delete(item)

    await db.commit()

    return {"message": "Cart cleared"}
