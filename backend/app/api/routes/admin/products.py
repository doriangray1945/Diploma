"""Admin product CRUD — variant-aware. Each Product has 1+ ProductVariant
SKUs (color/size/price/stock/images). Create/Update accept nested variants
payload; smart sync on PATCH (id → update, no id → insert, missing → delete).

Image upload: multipart endpoint `/admin/images/upload` writes to MinIO and
returns the public URL. Frontend stores returned URL on `variant.images`.
"""
import logging
import re
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import (
    APIRouter, Depends, File, HTTPException, Query, UploadFile, status,
)
from pydantic import BaseModel, Field
from sqlalchemy import or_, select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_admin
from app.core.database import get_db
from app.models import Product, ProductVariant
from app.schemas.admin import (
    BulkPriceUpdate,
    BulkStockUpdate,
    BulkUpdateResult,
)
from app.services.products import (
    bulk_update_prices,
    bulk_update_stock,
)
from app.services.storage import MinioStorage


log = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_admin)])


# ---------------------------------------------------------------------------
# Variant schemas
# ---------------------------------------------------------------------------


class VariantCreate(BaseModel):
    color: str | None = Field(default=None, max_length=50)
    size_label: str | None = Field(default=None, max_length=100)
    dimensions: dict | None = None
    price: float = Field(ge=0)
    old_price: float | None = Field(default=None, ge=0)
    stock_quantity: int = Field(default=0, ge=0)
    images: list[str] = Field(default_factory=list)
    sku: str | None = Field(default=None, max_length=100)
    is_default: bool = False


class VariantUpdate(BaseModel):
    # Optional `id` lets PATCH /admin/products/{id} sync existing rows;
    # rows without id are inserts, omitted ids are deletes.
    id: int | None = None
    color: str | None = Field(default=None, max_length=50)
    size_label: str | None = Field(default=None, max_length=100)
    dimensions: dict | None = None
    price: float | None = Field(default=None, ge=0)
    old_price: float | None = None
    stock_quantity: int | None = Field(default=None, ge=0)
    images: list[str] | None = None
    sku: str | None = Field(default=None, max_length=100)
    is_default: bool | None = None


class VariantResponse(BaseModel):
    id: int
    product_id: int
    color: str | None
    size_label: str | None
    dimensions: dict | None
    price: float
    old_price: float | None
    stock_quantity: int
    in_stock: bool
    images: list[str]
    sku: str | None
    is_default: bool

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Product schemas (variant-aware)
# ---------------------------------------------------------------------------


class AdminProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    category: str = Field(min_length=1, max_length=100)
    subcategory: str | None = None
    materials: str | None = None
    dimensions: dict | None = None
    is_popular: bool = False
    is_new: bool = False
    model_glb_url: str | None = Field(default=None, max_length=500)
    model_usdz_url: str | None = Field(default=None, max_length=500)
    variants: list[VariantCreate] = Field(min_length=1)


class AdminProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    category: str | None = Field(default=None, min_length=1, max_length=100)
    subcategory: str | None = None
    materials: str | None = None
    dimensions: dict | None = None
    is_popular: bool | None = None
    is_new: bool | None = None
    model_glb_url: str | None = Field(default=None, max_length=500)
    model_usdz_url: str | None = Field(default=None, max_length=500)
    # If provided, performs smart sync (id-match → update, no id → insert,
    # absent ids → delete). If None / not provided, variants are untouched.
    variants: list[VariantUpdate] | None = None


class AdminProductResponse(BaseModel):
    id: int
    name: str
    description: str
    category: str
    subcategory: str | None = None
    materials: str | None = None
    dimensions: dict | None = None
    rating: float
    reviews_count: int
    is_popular: bool
    is_new: bool
    model_glb_url: str | None = None
    model_usdz_url: str | None = None
    default_variant_id: int | None
    variants: list[VariantResponse]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AdminProductListResponse(BaseModel):
    items: list[AdminProductResponse]
    total: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _variant_to_response(v: ProductVariant) -> VariantResponse:
    return VariantResponse(
        id=v.id,
        product_id=v.product_id,
        color=v.color,
        size_label=v.size_label,
        dimensions=v.dimensions,
        price=float(v.price),
        old_price=float(v.old_price) if v.old_price is not None else None,
        stock_quantity=v.stock_quantity,
        in_stock=v.in_stock,
        images=list(v.images or []),
        sku=v.sku,
        is_default=v.is_default,
    )


def _product_to_response(p: Product) -> AdminProductResponse:
    variants = sorted(p.variants or [], key=lambda v: (not v.is_default, v.id))
    return AdminProductResponse(
        id=p.id, name=p.name, description=p.description,
        category=p.category, subcategory=p.subcategory,
        materials=p.materials, dimensions=p.dimensions,
        rating=float(p.rating or 0), reviews_count=p.reviews_count or 0,
        is_popular=p.is_popular, is_new=p.is_new,
        model_glb_url=p.model_glb_url, model_usdz_url=p.model_usdz_url,
        default_variant_id=p.default_variant_id,
        variants=[_variant_to_response(v) for v in variants],
        created_at=p.created_at, updated_at=p.updated_at,
    )


def _apply_variant_payload(target: ProductVariant, payload: VariantCreate | VariantUpdate) -> None:
    """Copy non-None fields onto the target variant. `is_default` handling is
    managed at the product level (only one default allowed)."""
    data = payload.model_dump(exclude_unset=True, exclude={"id"})
    for field, value in data.items():
        if value is None and isinstance(payload, VariantUpdate):
            # Skip None on update — means "keep existing value".
            continue
        setattr(target, field, value)
    # Auto-sync in_stock from stock_quantity.
    if data.get("stock_quantity") is not None:
        target.in_stock = (target.stock_quantity or 0) > 0


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=AdminProductListResponse)
async def list_products(
    db: Annotated[AsyncSession, Depends(get_db)],
    search: str | None = None,
    category: str | None = None,
    in_stock: bool | None = None,
    low_stock: bool = False,
    threshold: int = Query(5, ge=0, le=1000),
    sort_by: str = Query("created_at", pattern="^(created_at|name)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    query = select(Product).options(selectinload(Product.variants))
    if search:
        pat = f"%{search}%"
        query = query.where(or_(Product.name.ilike(pat), Product.description.ilike(pat)))
    if category:
        query = query.where(Product.category == category)

    # Stock filters operate on default variant (if any).
    if in_stock is not None:
        sub = (
            select(ProductVariant.product_id)
            .where(ProductVariant.in_stock == in_stock)
            .scalar_subquery()
        )
        # any-variant matches: the product has at least one variant in
        # the requested in_stock state. For the explicit "out of stock"
        # we want products where ALL variants are out — use NOT EXISTS.
        if in_stock:
            query = query.where(Product.id.in_(sub))
        else:
            in_stock_sub = (
                select(ProductVariant.product_id)
                .where(ProductVariant.in_stock == True)  # noqa: E712
                .scalar_subquery()
            )
            query = query.where(~Product.id.in_(in_stock_sub))
    if low_stock:
        sub = (
            select(ProductVariant.product_id)
            .where(
                ProductVariant.in_stock == True,  # noqa: E712
                ProductVariant.stock_quantity < threshold,
            )
            .scalar_subquery()
        )
        query = query.where(Product.id.in_(sub))

    total = int((await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one())

    sort_col = getattr(Product, sort_by)
    query = query.order_by(sort_col.desc() if sort_order == "desc" else sort_col.asc())
    query = query.offset((page - 1) * per_page).limit(per_page)

    rows = (await db.execute(query)).scalars().unique().all()
    return AdminProductListResponse(
        items=[_product_to_response(p) for p in rows],
        total=total,
    )


@router.get("/{product_id}", response_model=AdminProductResponse)
async def get_product(
    product_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Product).where(Product.id == product_id).options(selectinload(Product.variants))
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return _product_to_response(product)


@router.post("", response_model=AdminProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    body: AdminProductCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create a Product with one or more variants in a single transaction.
    The first variant flagged `is_default=True` (or the first one if none flagged)
    becomes the default; product.default_variant_id is set after variants are
    flushed and have ids."""
    product = Product(
        name=body.name,
        description=body.description,
        category=body.category,
        subcategory=body.subcategory,
        materials=body.materials,
        dimensions=body.dimensions,
        is_popular=body.is_popular,
        is_new=body.is_new,
        model_glb_url=body.model_glb_url,
        model_usdz_url=body.model_usdz_url,
    )
    db.add(product)
    await db.flush()  # need product.id

    # Decide default — exactly one is_default=True among variants.
    default_idx = next((i for i, v in enumerate(body.variants) if v.is_default), 0)
    variants_created: list[ProductVariant] = []
    for i, vc in enumerate(body.variants):
        v = ProductVariant(
            product_id=product.id,
            color=vc.color,
            size_label=vc.size_label,
            dimensions=vc.dimensions,
            price=vc.price,
            old_price=vc.old_price,
            stock_quantity=vc.stock_quantity,
            in_stock=(vc.stock_quantity or 0) > 0,
            images=list(vc.images or []),
            sku=vc.sku,
            is_default=(i == default_idx),
        )
        db.add(v)
        variants_created.append(v)
    await db.flush()  # populate variant ids

    product.default_variant_id = variants_created[default_idx].id

    await db.commit()
    # Refresh with eager-loaded variants for response.
    result = await db.execute(
        select(Product).where(Product.id == product.id).options(selectinload(Product.variants))
    )
    return _product_to_response(result.scalar_one())


@router.patch("/{product_id}", response_model=AdminProductResponse)
async def update_product(
    product_id: int,
    body: AdminProductUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Update product fields and (optionally) sync variants.

    Variant sync rules when `body.variants` is provided:
    - Existing variant in DB whose id is in payload → UPDATE.
    - Variant in payload without id → INSERT.
    - Variant in DB whose id is missing from payload → DELETE.
    Default variant: exactly one variant has is_default=True; set
    product.default_variant_id accordingly."""
    result = await db.execute(
        select(Product).where(Product.id == product_id).options(selectinload(Product.variants))
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")

    changed = body.model_dump(exclude_unset=True, exclude={"variants"})

    for field, value in changed.items():
        setattr(product, field, value)

    if body.variants is not None:
        await _sync_variants(db, product, body.variants)

    await db.commit()
    result = await db.execute(
        select(Product).where(Product.id == product.id).options(selectinload(Product.variants))
    )
    return _product_to_response(result.scalar_one())


async def _sync_variants(
    db: AsyncSession, product: Product, payload: list[VariantUpdate]
) -> None:
    existing_by_id = {v.id: v for v in product.variants}
    seen_ids: set[int] = set()

    # Decide default — choose first explicit is_default=True, else preserve current.
    explicit_default_idx = next(
        (i for i, p in enumerate(payload) if p.is_default is True), None
    )

    for i, p in enumerate(payload):
        if p.id and p.id in existing_by_id:
            v = existing_by_id[p.id]
            _apply_variant_payload(v, p)
            seen_ids.add(p.id)
        else:
            # New variant — insert. Required fields: price (others may default).
            if p.price is None:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "New variant requires `price`",
                )
            v = ProductVariant(
                product_id=product.id,
                color=p.color,
                size_label=p.size_label,
                dimensions=p.dimensions,
                price=p.price,
                old_price=p.old_price,
                stock_quantity=p.stock_quantity or 0,
                in_stock=(p.stock_quantity or 0) > 0,
                images=list(p.images or []),
                sku=p.sku,
                is_default=False,  # set below
            )
            db.add(v)
        # Track which entry corresponds to the chosen default index by index alignment.
        # We re-resolve by index after flush to grab the new id.

    # Delete variants that were not referenced.
    for vid, v in existing_by_id.items():
        if vid not in seen_ids:
            await db.delete(v)

    await db.flush()
    # Reload variants list (post-mutation) to set the default flag uniformly.
    result = await db.execute(
        select(ProductVariant).where(ProductVariant.product_id == product.id)
    )
    fresh = list(result.scalars().all())
    if not fresh:
        product.default_variant_id = None
        return
    # Map payload position → resulting variant. For updates we have id; for
    # inserts we identify by position relative to the list of just-flushed
    # variants ordered by id (the new ones got the highest ids).
    insert_count = sum(1 for p in payload if p.id is None)
    if insert_count:
        new_variants = sorted(
            [v for v in fresh if v.id not in seen_ids], key=lambda v: v.id
        )
    else:
        new_variants = []
    insert_idx_iter = iter(new_variants)
    target_default: ProductVariant | None = None
    for i, p in enumerate(payload):
        if p.id and p.id in seen_ids:
            v = existing_by_id[p.id]
        elif not p.id:
            try:
                v = next(insert_idx_iter)
            except StopIteration:
                continue
        else:
            continue
        if explicit_default_idx is not None and i == explicit_default_idx:
            target_default = v
    # Fallback: keep current default if it still exists, else first variant.
    if target_default is None:
        cur = next(
            (v for v in fresh if v.id == product.default_variant_id), None,
        ) or next((v for v in fresh if v.is_default), None) or fresh[0]
        target_default = cur

    for v in fresh:
        v.is_default = (v.id == target_default.id)
    product.default_variant_id = target_default.id


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


# --- Single-variant endpoints (for inline-edit on admin list) -------------


@router.post(
    "/{product_id}/variants",
    response_model=VariantResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_variant(
    product_id: int,
    body: VariantCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    v = ProductVariant(
        product_id=product_id,
        color=body.color,
        size_label=body.size_label,
        dimensions=body.dimensions,
        price=body.price,
        old_price=body.old_price,
        stock_quantity=body.stock_quantity,
        in_stock=(body.stock_quantity or 0) > 0,
        images=list(body.images or []),
        sku=body.sku,
        is_default=False,
    )
    db.add(v)
    await db.flush()
    if body.is_default:
        # Mark all others non-default.
        await _set_default_variant(db, product_id, v.id)
    await db.commit()
    await db.refresh(v)
    return _variant_to_response(v)


@router.patch("/variants/{variant_id}", response_model=VariantResponse)
async def update_variant(
    variant_id: int,
    body: VariantUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    v = await db.get(ProductVariant, variant_id)
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Variant not found")
    _apply_variant_payload(v, body)
    if body.is_default is True:
        await _set_default_variant(db, v.product_id, v.id)
    await db.commit()
    await db.refresh(v)
    return _variant_to_response(v)


async def _set_default_variant(db: AsyncSession, product_id: int, variant_id: int) -> None:
    # Mark `variant_id` default, all others not.
    result = await db.execute(
        select(ProductVariant).where(ProductVariant.product_id == product_id)
    )
    for v in result.scalars().all():
        v.is_default = (v.id == variant_id)
    product = await db.get(Product, product_id)
    if product:
        product.default_variant_id = variant_id


# --- Image upload to MinIO -------------------------------------------------


_SAFE_NAME = re.compile(r"[^a-zA-Z0-9._-]+")


@router.post("/images/upload")
async def upload_image(
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
):
    """Upload one image to MinIO bucket and return its public URL.
    Frontend keeps URL on `variant.images` and submits it on save."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "Only image/* uploads are accepted")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 10 MB)")

    # Pick extension from content_type rather than filename so we don't
    # trust client-provided suffixes.
    ext_map = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif"}
    ext = ext_map.get(file.content_type, "bin")

    safe_name = _SAFE_NAME.sub("_", (file.filename or "upload").rsplit(".", 1)[0])[:40]
    key = f"admin/{datetime.utcnow():%Y%m%d}/{uuid.uuid4().hex[:12]}-{safe_name}.{ext}"

    storage = MinioStorage()
    url = storage.upload_file(key, data, content_type=file.content_type)
    return {"url": url, "key": key}


# --- Bulk endpoints (used by chat tools) ----------------------------------


@router.post("/bulk/stock", response_model=BulkUpdateResult)
async def bulk_update_stock_endpoint(
    payload: BulkStockUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Bulk-update stock for matching variants.
    Used by chat tool `update_stock`."""
    affected = await bulk_update_stock(db, payload.filter, payload.operation, payload.quantity)
    return BulkUpdateResult(affected_count=affected, operation=payload.operation)


@router.post("/bulk/prices", response_model=BulkUpdateResult)
async def bulk_update_prices_endpoint(
    payload: BulkPriceUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Bulk-update prices for matching variants.
    Used by chat tool `update_prices`."""
    affected, delta = await bulk_update_prices(db, payload.filter, payload.operation, payload.value)
    return BulkUpdateResult(
        affected_count=affected,
        operation=payload.operation,
        revenue_impact=float(delta),
    )
