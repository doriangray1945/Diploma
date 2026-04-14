from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models import CartItem, Product, User
from app.schemas import CartItemCreate, CartItemUpdate, CartResponse, CartItemResponse, ProductResponse
from app.api.deps import get_current_user

router = APIRouter()


@router.get("", response_model=CartResponse)
async def get_cart(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    result = await db.execute(
        select(CartItem)
        .where(CartItem.user_id == current_user.id)
        .options(selectinload(CartItem.product))
    )
    cart_items = result.scalars().all()

    items = []
    total = 0.0
    for item in cart_items:
        product = item.product
        item_total = float(product.price) * item.quantity
        total += item_total

        items.append(CartItemResponse(
            id=item.id,
            product_id=item.product_id,
            quantity=item.quantity,
            created_at=item.created_at,
            product=ProductResponse(
                id=product.id,
                name=product.name,
                description=product.description,
                price=float(product.price),
                old_price=float(product.old_price) if product.old_price else None,
                category=product.category,
                subcategory=product.subcategory,
                images=product.images,
                dimensions=product.dimensions,
                materials=product.materials,
                color=product.color,
                in_stock=product.in_stock,
                stock_quantity=product.stock_quantity,
                rating=float(product.rating),
                reviews_count=product.reviews_count,
                is_popular=product.is_popular,
                is_new=product.is_new,
                created_at=product.created_at,
                is_favorite=False
            )
        ))

    return CartResponse(
        items=items,
        total=round(total, 2),
        items_count=len(items)
    )


@router.post("/items", response_model=CartItemResponse)
async def add_to_cart(
    item_data: CartItemCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    # Check product exists
    product_result = await db.execute(select(Product).where(Product.id == item_data.product_id))
    product = product_result.scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Check if already in cart
    existing_result = await db.execute(
        select(CartItem).where(
            CartItem.user_id == current_user.id,
            CartItem.product_id == item_data.product_id
        )
    )
    existing_item = existing_result.scalar_one_or_none()

    if existing_item:
        # Update quantity
        existing_item.quantity += item_data.quantity
        await db.commit()
        await db.refresh(existing_item)
        cart_item = existing_item
    else:
        # Create new cart item
        cart_item = CartItem(
            user_id=current_user.id,
            product_id=item_data.product_id,
            quantity=item_data.quantity
        )
        db.add(cart_item)
        await db.commit()
        await db.refresh(cart_item)

    return CartItemResponse(
        id=cart_item.id,
        product_id=cart_item.product_id,
        quantity=cart_item.quantity,
        created_at=cart_item.created_at,
        product=ProductResponse(
            id=product.id,
            name=product.name,
            description=product.description,
            price=float(product.price),
            old_price=float(product.old_price) if product.old_price else None,
            category=product.category,
            subcategory=product.subcategory,
            images=product.images,
            dimensions=product.dimensions,
            materials=product.materials,
            color=product.color,
            in_stock=product.in_stock,
            stock_quantity=product.stock_quantity,
            rating=float(product.rating),
            reviews_count=product.reviews_count,
            is_popular=product.is_popular,
            is_new=product.is_new,
            created_at=product.created_at,
            is_favorite=False
        )
    )


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
        .options(selectinload(CartItem.product))
    )
    cart_item = result.scalar_one_or_none()

    if not cart_item:
        raise HTTPException(status_code=404, detail="Cart item not found")

    if item_data.quantity <= 0:
        await db.delete(cart_item)
        await db.commit()
        raise HTTPException(status_code=204, detail="Item removed from cart")

    cart_item.quantity = item_data.quantity
    await db.commit()
    await db.refresh(cart_item)

    product = cart_item.product
    return CartItemResponse(
        id=cart_item.id,
        product_id=cart_item.product_id,
        quantity=cart_item.quantity,
        created_at=cart_item.created_at,
        product=ProductResponse(
            id=product.id,
            name=product.name,
            description=product.description,
            price=float(product.price),
            old_price=float(product.old_price) if product.old_price else None,
            category=product.category,
            subcategory=product.subcategory,
            images=product.images,
            dimensions=product.dimensions,
            materials=product.materials,
            color=product.color,
            in_stock=product.in_stock,
            stock_quantity=product.stock_quantity,
            rating=float(product.rating),
            reviews_count=product.reviews_count,
            is_popular=product.is_popular,
            is_new=product.is_new,
            created_at=product.created_at,
            is_favorite=False
        )
    )


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
