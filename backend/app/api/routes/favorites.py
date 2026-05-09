"""Favorites endpoints — variant-aware. Each favorite references a specific
SKU; the user is favoriting "Брюквил серый 3-местный", not just "Брюквил".
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models import Favorite, Product, ProductVariant, User
from app.schemas import FavoriteResponse, FavoriteListResponse
from app.api.deps import get_current_user
from app.api.routes.products import _serialize_product

router = APIRouter()


def _serialize_favorite(fav: Favorite, all_fav_variant_ids: set[int]) -> FavoriteResponse:
    variant = fav.variant
    product = variant.product
    return FavoriteResponse(
        id=fav.id,
        variant_id=fav.variant_id,
        product_id=product.id,
        selected_color=variant.color,
        selected_size=variant.size_label,
        created_at=fav.created_at,
        product=_serialize_product(product, all_fav_variant_ids),
    )


async def _user_favorite_variant_ids(db: AsyncSession, user_id: int) -> set[int]:
    fav_result = await db.execute(
        select(Favorite.variant_id).where(Favorite.user_id == user_id)
    )
    return set(fav_result.scalars().all())


@router.get("", response_model=FavoriteListResponse)
async def get_favorites(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    result = await db.execute(
        select(Favorite)
        .where(Favorite.user_id == current_user.id)
        .options(
            selectinload(Favorite.variant)
            .selectinload(ProductVariant.product)
            .selectinload(Product.variants)
        )
        .order_by(Favorite.created_at.desc())
    )
    favorites = list(result.scalars().all())
    fav_ids = {f.variant_id for f in favorites}
    items = [_serialize_favorite(f, fav_ids) for f in favorites]
    return FavoriteListResponse(items=items, total=len(items))


@router.post("/{variant_id}", response_model=FavoriteResponse)
async def add_to_favorites(
    variant_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    variant_result = await db.execute(
        select(ProductVariant).where(ProductVariant.id == variant_id)
    )
    variant = variant_result.scalar_one_or_none()
    if not variant:
        raise HTTPException(status_code=404, detail="Product variant not found")

    existing = (await db.execute(
        select(Favorite).where(
            Favorite.user_id == current_user.id,
            Favorite.variant_id == variant_id,
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Variant already in favorites")

    favorite = Favorite(user_id=current_user.id, variant_id=variant_id)
    db.add(favorite)
    await db.commit()
    await db.refresh(favorite)

    favorite = (await db.execute(
        select(Favorite)
        .where(Favorite.id == favorite.id)
        .options(
            selectinload(Favorite.variant)
            .selectinload(ProductVariant.product)
            .selectinload(Product.variants)
        )
    )).scalar_one()

    fav_ids = await _user_favorite_variant_ids(db, current_user.id)
    return _serialize_favorite(favorite, fav_ids)


@router.delete("/{variant_id}")
async def remove_from_favorites(
    variant_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    result = await db.execute(
        select(Favorite).where(
            Favorite.user_id == current_user.id,
            Favorite.variant_id == variant_id,
        )
    )
    favorite = result.scalar_one_or_none()

    if not favorite:
        raise HTTPException(status_code=404, detail="Variant not in favorites")

    await db.delete(favorite)
    await db.commit()

    return {"message": "Removed from favorites"}
