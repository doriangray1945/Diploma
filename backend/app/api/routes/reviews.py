"""Reviews on products. One review per (user, product). User can only post
a review for a product they have actually received (at least one order in
status `delivered` that contained this product). Product.rating and
Product.reviews_count are recomputed from this table after every CRUD op,
so the catalog summary is always consistent with the underlying data.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import Order, OrderItem, Product, Review, User
from app.schemas import (
    ReviewCreate,
    ReviewEligibility,
    ReviewListResponse,
    ReviewResponse,
    ReviewUpdate,
)

router = APIRouter()


# ─── helpers ──────────────────────────────────────────────────────────


def _to_response(review: Review, user_name: str) -> ReviewResponse:
    return ReviewResponse(
        id=review.id,
        user_id=review.user_id,
        user_name=user_name,
        rating=review.rating,
        text=review.text,
        created_at=review.created_at,
        updated_at=review.updated_at,
    )


async def _user_can_review(db: AsyncSession, user_id: int, product_id: int) -> bool:
    """True if user has at least one delivered order containing this product."""
    q = (
        select(func.count())
        .select_from(Order)
        .join(OrderItem, OrderItem.order_id == Order.id)
        .where(
            Order.user_id == user_id,
            Order.status == "delivered",
            OrderItem.product_id == product_id,
        )
    )
    return ((await db.execute(q)).scalar_one() or 0) > 0


async def _recompute_product_rating(db: AsyncSession, product_id: int) -> None:
    """Refresh Product.rating and Product.reviews_count from the reviews
    table. Called after every review CRUD so the cached aggregates on the
    catalog row never drift from the actual reviews."""
    q = select(
        func.coalesce(func.avg(Review.rating), 0),
        func.count(Review.id),
    ).where(Review.product_id == product_id)
    avg_rating, count = (await db.execute(q)).one()
    product = await db.get(Product, product_id)
    if product is not None:
        product.rating = round(float(avg_rating or 0), 1)
        product.reviews_count = int(count or 0)


async def _own_review(
    db: AsyncSession, user_id: int, product_id: int
) -> Review | None:
    result = await db.execute(
        select(Review).where(
            Review.user_id == user_id,
            Review.product_id == product_id,
        )
    )
    return result.scalar_one_or_none()


# ─── endpoints ────────────────────────────────────────────────────────


@router.get("/{product_id}/reviews", response_model=ReviewListResponse)
async def list_reviews(
    product_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
):
    """Public — anyone can read reviews. Newest first."""
    # 404 if product missing — keeps API predictable for the UI.
    if (await db.get(Product, product_id)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")

    total_q = select(func.count(Review.id)).where(Review.product_id == product_id)
    total = (await db.execute(total_q)).scalar_one()

    offset = (page - 1) * per_page
    q = (
        select(Review, User.name)
        .join(User, User.id == Review.user_id)
        .where(Review.product_id == product_id)
        .order_by(Review.created_at.desc())
        .limit(per_page)
        .offset(offset)
    )
    rows = (await db.execute(q)).all()
    items = [_to_response(r, name) for r, name in rows]
    return ReviewListResponse(items=items, total=total)


@router.get("/{product_id}/reviews/eligibility", response_model=ReviewEligibility)
async def review_eligibility(
    product_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    if (await db.get(Product, product_id)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")

    can_review = await _user_can_review(db, current_user.id, product_id)
    own = await _own_review(db, current_user.id, product_id)
    my_review = _to_response(own, current_user.name) if own else None
    return ReviewEligibility(
        can_review=can_review,
        has_review=own is not None,
        my_review=my_review,
    )


@router.post(
    "/{product_id}/reviews",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_review(
    product_id: int,
    body: ReviewCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    if (await db.get(Product, product_id)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")

    if not await _user_can_review(db, current_user.id, product_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Оставить отзыв можно только после доставки заказа с этим товаром",
        )

    if await _own_review(db, current_user.id, product_id) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Вы уже оставили отзыв на этот товар",
        )

    review = Review(
        user_id=current_user.id,
        product_id=product_id,
        rating=body.rating,
        text=body.text,
    )
    db.add(review)
    await db.flush()
    await _recompute_product_rating(db, product_id)
    await db.commit()
    await db.refresh(review)
    return _to_response(review, current_user.name)


@router.patch("/{product_id}/reviews", response_model=ReviewResponse)
async def update_review(
    product_id: int,
    body: ReviewUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    review = await _own_review(db, current_user.id, product_id)
    if review is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Review not found")

    data = body.model_dump(exclude_unset=True)
    if "rating" in data and data["rating"] is not None:
        review.rating = data["rating"]
    if "text" in data:
        review.text = data["text"]

    await db.flush()
    await _recompute_product_rating(db, product_id)
    await db.commit()
    await db.refresh(review)
    return _to_response(review, current_user.name)


@router.delete("/{product_id}/reviews", status_code=status.HTTP_204_NO_CONTENT)
async def delete_review(
    product_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    review = await _own_review(db, current_user.id, product_id)
    if review is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Review not found")
    await db.delete(review)
    await db.flush()
    await _recompute_product_rating(db, product_id)
    await db.commit()
    return None
