import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.database import get_db
from app.models import Product
from app.schemas.admin import (
    BulkPriceUpdate,
    BulkStockUpdate,
    BulkUpdateResult,
)
from app.services.embeddings import embed
from app.services.products import (
    EMBEDDING_FIELDS,
    build_product_text,
    bulk_update_prices,
    bulk_update_stock,
)


log = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_admin)])


class AdminProductBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    price: float = Field(ge=0)
    old_price: float | None = None
    category: str = Field(min_length=1, max_length=100)
    subcategory: str | None = None
    images: list[str] = Field(default_factory=list)
    dimensions: str | None = None
    materials: str | None = None
    color: str | None = None
    in_stock: bool = True
    stock_quantity: int = Field(default=0, ge=0)
    is_popular: bool = False
    is_new: bool = False
    model_glb_url: str | None = Field(default=None, max_length=500)
    model_usdz_url: str | None = Field(default=None, max_length=500)


class AdminProductCreate(AdminProductBase):
    pass


class AdminProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    price: float | None = Field(default=None, ge=0)
    old_price: float | None = None
    category: str | None = Field(default=None, min_length=1, max_length=100)
    subcategory: str | None = None
    images: list[str] | None = None
    dimensions: str | None = None
    materials: str | None = None
    color: str | None = None
    in_stock: bool | None = None
    stock_quantity: int | None = Field(default=None, ge=0)
    is_popular: bool | None = None
    is_new: bool | None = None
    model_glb_url: str | None = Field(default=None, max_length=500)
    model_usdz_url: str | None = Field(default=None, max_length=500)


class AdminProductResponse(BaseModel):
    id: int
    name: str
    description: str
    price: float
    old_price: float | None = None
    category: str
    subcategory: str | None = None
    images: list[str] = Field(default_factory=list)
    dimensions: str | None = None
    materials: str | None = None
    color: str | None = None
    in_stock: bool
    stock_quantity: int
    rating: float
    reviews_count: int
    is_popular: bool
    is_new: bool
    model_glb_url: str | None = None
    model_usdz_url: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AdminProductListResponse(BaseModel):
    items: list[AdminProductResponse]
    total: int


def _to_response(p: Product) -> AdminProductResponse:
    return AdminProductResponse(
        id=p.id, name=p.name, description=p.description,
        price=float(p.price),
        old_price=float(p.old_price) if p.old_price is not None else None,
        category=p.category, subcategory=p.subcategory,
        images=list(p.images or []),
        dimensions=p.dimensions, materials=p.materials, color=p.color,
        in_stock=p.in_stock, stock_quantity=p.stock_quantity,
        rating=float(p.rating or 0), reviews_count=p.reviews_count or 0,
        is_popular=p.is_popular, is_new=p.is_new,
        model_glb_url=p.model_glb_url, model_usdz_url=p.model_usdz_url,
        created_at=p.created_at, updated_at=p.updated_at,
    )


async def _compute_embedding(product: Product) -> list[float] | None:
    text = build_product_text(product)
    return await embed(text)


@router.get("", response_model=AdminProductListResponse)
async def list_products(
    db: Annotated[AsyncSession, Depends(get_db)],
    search: str | None = None,
    category: str | None = None,
    in_stock: bool | None = None,
    low_stock: bool = False,
    threshold: int = Query(5, ge=0, le=1000),
    sort_by: str = Query("created_at", pattern="^(created_at|price|name|stock_quantity)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    query = select(Product)
    if search:
        pat = f"%{search}%"
        query = query.where(or_(Product.name.ilike(pat), Product.description.ilike(pat)))
    if category:
        query = query.where(Product.category == category)
    if in_stock is not None:
        query = query.where(Product.in_stock == in_stock)
    if low_stock:
        query = query.where(Product.in_stock == True, Product.stock_quantity < threshold)  # noqa: E712

    total = int((await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one())

    sort_col = getattr(Product, sort_by)
    query = query.order_by(sort_col.desc() if sort_order == "desc" else sort_col.asc())
    query = query.offset((page - 1) * per_page).limit(per_page)

    rows = (await db.execute(query)).scalars().all()
    return AdminProductListResponse(items=[_to_response(p) for p in rows], total=total)


@router.post("", response_model=AdminProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    body: AdminProductCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    data: dict[str, Any] = body.model_dump()
    product = Product(**data)
    # Auto-flip in_stock if quantity is zero (consistency with /admin/inventory)
    if product.stock_quantity == 0:
        product.in_stock = False
    db.add(product)
    await db.flush()  # get id

    embedding = await _compute_embedding(product)
    if embedding is not None:
        product.embedding = embedding
    else:
        log.warning("[ADMIN] product %d created without embedding (Ollama unavailable)", product.id)

    await db.commit()
    await db.refresh(product)
    return _to_response(product)


@router.patch("/{product_id}", response_model=AdminProductResponse)
async def update_product(
    product_id: int,
    body: AdminProductUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")

    changed = body.model_dump(exclude_unset=True)
    needs_embedding = bool(EMBEDDING_FIELDS & changed.keys())

    for field, value in changed.items():
        setattr(product, field, value)

    # Keep stock flag consistent with quantity
    if "stock_quantity" in changed and product.stock_quantity == 0:
        product.in_stock = False
    if "stock_quantity" in changed and product.stock_quantity > 0 and "in_stock" not in changed:
        product.in_stock = True

    if needs_embedding:
        embedding = await _compute_embedding(product)
        if embedding is not None:
            product.embedding = embedding

    await db.commit()
    await db.refresh(product)
    return _to_response(product)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    await db.delete(product)
    await db.commit()
    return None


@router.post("/bulk-update-stock", response_model=BulkUpdateResult)
async def bulk_update_stock_endpoint(
    payload: BulkStockUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Bulk-update stock_quantity for products matching filter.

    Used by chat tool `update_stock`. operation:
    - set      → SET stock = quantity
    - add      → SET stock = stock + quantity
    - subtract → SET stock = MAX(0, stock - quantity)
    Auto-syncs in_stock = (stock > 0)."""
    affected = await bulk_update_stock(db, payload.filter, payload.operation, payload.quantity)
    return BulkUpdateResult(affected_count=affected, operation=payload.operation)


@router.post("/bulk-update-prices", response_model=BulkUpdateResult)
async def bulk_update_prices_endpoint(
    payload: BulkPriceUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Bulk-update prices for products matching filter.

    Used by chat tool `update_prices`. operation:
    - discount  → -value% from each price
    - markup    → +value% to each price
    - set_price → SET price = value (RUB, absolute)
    Saves current price into old_price for UI discount-strike display."""
    affected, delta = await bulk_update_prices(db, payload.filter, payload.operation, payload.value)
    return BulkUpdateResult(
        affected_count=affected,
        operation=payload.operation,
        revenue_impact=float(delta),
    )
