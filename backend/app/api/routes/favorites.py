from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models import Favorite, Product, User
from app.schemas import FavoriteResponse, FavoriteListResponse, ProductResponse
from app.api.deps import get_current_user

router = APIRouter()


@router.get("", response_model=FavoriteListResponse)
async def get_favorites(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    result = await db.execute(
        select(Favorite)
        .where(Favorite.user_id == current_user.id)
        .options(selectinload(Favorite.product))
        .order_by(Favorite.created_at.desc())
    )
    favorites = result.scalars().all()

    items = []
    for fav in favorites:
        product = fav.product
        items.append(FavoriteResponse(
            id=fav.id,
            product_id=fav.product_id,
            created_at=fav.created_at,
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
                is_favorite=True
            )
        ))

    return FavoriteListResponse(items=items, total=len(items))


@router.post("/{product_id}", response_model=FavoriteResponse)
async def add_to_favorites(
    product_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    # Check product exists
    product_result = await db.execute(select(Product).where(Product.id == product_id))
    product = product_result.scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Check if already in favorites
    existing_result = await db.execute(
        select(Favorite).where(
            Favorite.user_id == current_user.id,
            Favorite.product_id == product_id
        )
    )
    if existing_result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Product already in favorites")

    # Add to favorites
    favorite = Favorite(user_id=current_user.id, product_id=product_id)
    db.add(favorite)
    await db.commit()
    await db.refresh(favorite)

    return FavoriteResponse(
        id=favorite.id,
        product_id=favorite.product_id,
        created_at=favorite.created_at,
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
            is_favorite=True
        )
    )


@router.delete("/{product_id}")
async def remove_from_favorites(
    product_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    result = await db.execute(
        select(Favorite).where(
            Favorite.user_id == current_user.id,
            Favorite.product_id == product_id
        )
    )
    favorite = result.scalar_one_or_none()

    if not favorite:
        raise HTTPException(status_code=404, detail="Product not in favorites")

    await db.delete(favorite)
    await db.commit()

    return {"message": "Removed from favorites"}
