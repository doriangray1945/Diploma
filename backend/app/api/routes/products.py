"""Public catalog endpoints. Variant-aware: filtering on price/color/in_stock
walks through ProductVariant; serialization eager-loads variants[] and
exposes a default-variant snapshot at the top level for legacy frontend
code that expects product.price/images/color directly.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_, select, func, exists
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.semantic_config import MATERIAL_GROUPS, resolve_material
from app.models import Product, ProductVariant, Favorite, User, Category
from app.schemas import ProductResponse, ProductListResponse, ProductVariantResponse, CategoryResponse
from app.api.deps import get_current_user_optional
from app.services.products import apply_search_filter

router = APIRouter()


def _serialize_product(product: Product, favorite_variant_ids: set[int]) -> ProductResponse:
    """Build ProductResponse with default-variant snapshot fields populated."""
    variants_sorted = sorted(
        product.variants, key=lambda v: (not v.is_default, v.id)
    )
    default = next(
        (v for v in variants_sorted if v.is_default),
        variants_sorted[0] if variants_sorted else None,
    )
    is_favorite = any(v.id in favorite_variant_ids for v in variants_sorted)
    return ProductResponse(
        id=product.id,
        name=product.name,
        description=product.description,
        category=product.category,
        subcategory=product.subcategory,
        materials=product.materials,
        dimensions=product.dimensions,
        rating=float(product.rating),
        reviews_count=product.reviews_count,
        is_popular=product.is_popular,
        is_new=product.is_new,
        model_glb_url=product.model_glb_url,
        model_usdz_url=product.model_usdz_url,
        created_at=product.created_at,
        is_favorite=is_favorite,
        default_variant_id=product.default_variant_id,
        variants=[ProductVariantResponse.model_validate(v) for v in variants_sorted],
        # Default-variant snapshot (legacy compat for frontend reading product.price etc).
        price=float(default.price) if default else 0.0,
        old_price=float(default.old_price) if default and default.old_price else None,
        images=default.images if default else [],
        color=default.color if default else None,
        in_stock=default.in_stock if default else False,
        stock_quantity=default.stock_quantity if default else 0,
    )


@router.get("", response_model=ProductListResponse)
async def get_products(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User | None, Depends(get_current_user_optional)],
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=100),
    category: str | None = None,
    subcategory: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    color: list[str] | None = Query(None),
    material: list[str] | None = Query(None),
    in_stock: bool | None = None,
    is_popular: bool | None = None,
    is_new: bool | None = None,
    search: str | None = None,
    sort_by: str = Query("created_at", pattern="^(created_at|price|rating|name)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$")
):
    base = select(Product)
    if category:
        base = base.where(Product.category == category)
    if subcategory:
        base = base.where(Product.subcategory == subcategory)

    # Variant-level filters: price/color/in_stock are EXISTS subqueries on
    # product_variants. A product passes if at least one of its variants matches.
    variant_filters: list = []
    if min_price is not None:
        variant_filters.append(ProductVariant.price >= min_price)
    if max_price is not None:
        variant_filters.append(ProductVariant.price <= max_price)
    if in_stock is not None:
        variant_filters.append(ProductVariant.in_stock == in_stock)
    if color:
        variant_filters.append(or_(*[
            ProductVariant.color.ilike(f"%{c}%") for c in color if c
        ]))
    if variant_filters:
        base = base.where(exists().where(
            ProductVariant.product_id == Product.id, *variant_filters
        ))

    if material:
        all_substrings: list[str] = []
        for m in material:
            all_substrings.extend(resolve_material(m))
        if all_substrings:
            base = base.where(or_(*[
                Product.materials.ilike(f"%{s}%") for s in all_substrings
            ]))
    if is_popular is not None:
        base = base.where(Product.is_popular == is_popular)
    if is_new is not None:
        base = base.where(Product.is_new == is_new)

    # BM25 full-text search via pg_search (operates on Product fields).
    query = apply_search_filter(base, search)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    if not search:
        # `price` is now on variant — sort_by=price uses default variant's price.
        if sort_by == "price":
            # Subquery: default variant's price per product.
            default_price_sq = (
                select(ProductVariant.price)
                .where(
                    ProductVariant.product_id == Product.id,
                    ProductVariant.is_default == True,  # noqa: E712
                )
                .scalar_subquery()
            )
            order_col = default_price_sq
        else:
            order_col = getattr(Product, sort_by)
        query = query.order_by(order_col.desc() if sort_order == "desc" else order_col.asc())

    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page).options(selectinload(Product.variants))

    result = await db.execute(query)
    products = result.scalars().all()

    # User's favorites — at variant level.
    favorite_variant_ids: set[int] = set()
    if current_user:
        fav_result = await db.execute(
            select(Favorite.variant_id).where(Favorite.user_id == current_user.id)
        )
        favorite_variant_ids = set(fav_result.scalars().all())

    items = [_serialize_product(p, favorite_variant_ids) for p in products]

    pages = (total + per_page - 1) // per_page

    return ProductListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


@router.get("/filter-options")
async def get_filter_options(
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Return enum values for the catalog filter UI: categories, materials,
    colors, price range. Color and price come from variant table now.
    """
    cat_rows = (await db.execute(
        select(Product.category).distinct()
    )).scalars().all()
    color_rows = (await db.execute(
        select(ProductVariant.color).distinct().where(ProductVariant.color.isnot(None))
    )).scalars().all()
    price_row = (await db.execute(
        select(func.min(ProductVariant.price), func.max(ProductVariant.price))
    )).one()

    return {
        "categories": sorted([c for c in cat_rows if c]),
        "colors":     sorted([c for c in color_rows if c]),
        "materials":  list(MATERIAL_GROUPS.keys()),
        "price_range": {
            "min": float(price_row[0] or 0),
            "max": float(price_row[1] or 0),
        },
    }


@router.get("/categories", response_model=list[CategoryResponse])
async def get_categories(
    db: Annotated[AsyncSession, Depends(get_db)]
):
    cats = (await db.execute(
        select(Category).order_by(Category.sort_order, Category.name)
    )).scalars().all()

    counts_rows = (await db.execute(
        select(Product.category, func.count(Product.id)).group_by(Product.category)
    )).all()
    counts = {row[0]: int(row[1]) for row in counts_rows}

    categories: list[CategoryResponse] = []
    for cat in cats:
        sub_result = await db.execute(
            select(Product.subcategory)
            .where(Product.category == cat.name, Product.subcategory.isnot(None))
            .distinct()
        )
        subcategories = [s for s in sub_result.scalars().all() if s]
        categories.append(CategoryResponse(
            name=cat.name,
            count=counts.get(cat.name, 0),
            subcategories=subcategories,
        ))
    return categories


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User | None, Depends(get_current_user_optional)]
):
    result = await db.execute(
        select(Product)
        .where(Product.id == product_id)
        .options(selectinload(Product.variants))
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    favorite_variant_ids: set[int] = set()
    if current_user:
        fav_result = await db.execute(
            select(Favorite.variant_id).where(Favorite.user_id == current_user.id)
        )
        favorite_variant_ids = set(fav_result.scalars().all())

    return _serialize_product(product, favorite_variant_ids)
