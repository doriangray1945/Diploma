from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.database import get_db
from app.models import Category, Product

router = APIRouter(dependencies=[Depends(require_admin)])


class CategoryResponse(BaseModel):
    id: int
    name: str
    slug: str | None = None
    sort_order: int = 0
    created_at: datetime
    products_count: int = 0


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    slug: str | None = None
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    slug: str | None = None
    sort_order: int | None = None


@router.get("", response_model=list[CategoryResponse])
async def list_categories(db: Annotated[AsyncSession, Depends(get_db)]):
    counts_q = (
        select(Product.category, func.count(Product.id).label("c"))
        .group_by(Product.category)
    )
    counts = {row[0]: int(row[1]) for row in (await db.execute(counts_q)).all()}

    rows = (await db.execute(select(Category).order_by(Category.sort_order, Category.name))).scalars().all()
    return [
        CategoryResponse(
            id=c.id, name=c.name, slug=c.slug, sort_order=c.sort_order,
            created_at=c.created_at, products_count=counts.get(c.name, 0),
        )
        for c in rows
    ]


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    body: CategoryCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    cat = Category(name=body.name, slug=body.slug, sort_order=body.sort_order)
    db.add(cat)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Category with this name already exists")
    await db.refresh(cat)
    return CategoryResponse(
        id=cat.id, name=cat.name, slug=cat.slug, sort_order=cat.sort_order,
        created_at=cat.created_at, products_count=0,
    )


@router.patch("/{cat_id}", response_model=CategoryResponse)
async def update_category(
    cat_id: int,
    body: CategoryUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    cat = await db.get(Category, cat_id)
    if cat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")

    old_name = cat.name
    changed = body.model_dump(exclude_unset=True)
    for field, value in changed.items():
        setattr(cat, field, value)

    try:
        # If name changed, also rename it on existing products so the catalog
        # filter keeps working.
        if "name" in changed and changed["name"] != old_name:
            await db.execute(
                Product.__table__.update()
                .where(Product.category == old_name)
                .values(category=changed["name"])
            )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Category with this name already exists")
    await db.refresh(cat)
    count = int(
        (await db.execute(select(func.count(Product.id)).where(Product.category == cat.name))).scalar_one()
    )
    return CategoryResponse(
        id=cat.id, name=cat.name, slug=cat.slug, sort_order=cat.sort_order,
        created_at=cat.created_at, products_count=count,
    )


@router.delete("/{cat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    cat_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    cat = await db.get(Category, cat_id)
    if cat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    in_use = int(
        (await db.execute(select(func.count(Product.id)).where(Product.category == cat.name))).scalar_one()
    )
    if in_use:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot delete: {in_use} product(s) still use this category",
        )
    await db.delete(cat)
    await db.commit()
    return None
