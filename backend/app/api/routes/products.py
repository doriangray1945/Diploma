from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_, select, func

from app.core.database import get_db
from app.core.semantic_config import MATERIAL_GROUPS, resolve_material
from app.models import Product, Favorite, User, Category
from app.schemas import ProductResponse, ProductListResponse, CategoryResponse
from app.api.deps import get_current_user_optional
from app.services.products import apply_search_filter

router = APIRouter()


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
    if min_price is not None:
        base = base.where(Product.price >= min_price)
    if max_price is not None:
        base = base.where(Product.price <= max_price)
    if color:
        # FastAPI's `Query(None)` for `list[str]` already returns a list.
        # Multi-value color: OR'd ILIKE.
        base = base.where(or_(*[
            Product.color.ilike(f"%{c}%") for c in color if c
        ]))
    if material:
        # Multi-value material: each label expands via MATERIAL_GROUPS, all
        # substrings OR'd into a single big WHERE.
        all_substrings: list[str] = []
        for m in material:
            all_substrings.extend(resolve_material(m))
        if all_substrings:
            base = base.where(or_(*[
                Product.materials.ilike(f"%{s}%") for s in all_substrings
            ]))
    if in_stock is not None:
        base = base.where(Product.in_stock == in_stock)
    if is_popular is not None:
        base = base.where(Product.is_popular == is_popular)
    if is_new is not None:
        base = base.where(Product.is_new == is_new)

    # Apply BM25 full-text search via pg_search. When `search` is set the
    # query is reordered by `paradedb.score()` inside the helper; when it's
    # not, we honour the user's sort_by/sort_order below.
    query = apply_search_filter(base, search)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    if not search:
        sort_column = getattr(Product, sort_by)
        query = query.order_by(sort_column.desc() if sort_order == "desc" else sort_column.asc())

    # Pagination
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    result = await db.execute(query)
    products = result.scalars().all()

    # Get user's favorites
    favorite_product_ids = set()
    if current_user:
        fav_result = await db.execute(
            select(Favorite.product_id).where(Favorite.user_id == current_user.id)
        )
        favorite_product_ids = set(fav_result.scalars().all())

    # Build response
    items = []
    for product in products:
        product_dict = {
            "id": product.id,
            "name": product.name,
            "description": product.description,
            "price": float(product.price),
            "old_price": float(product.old_price) if product.old_price else None,
            "category": product.category,
            "subcategory": product.subcategory,
            "images": product.images,
            "dimensions": product.dimensions,
            "materials": product.materials,
            "color": product.color,
            "in_stock": product.in_stock,
            "stock_quantity": product.stock_quantity,
            "rating": float(product.rating),
            "reviews_count": product.reviews_count,
            "is_popular": product.is_popular,
            "is_new": product.is_new,
            "model_glb_url": product.model_glb_url,
            "model_usdz_url": product.model_usdz_url,
            "created_at": product.created_at,
            "is_favorite": product.id in favorite_product_ids
        }
        items.append(ProductResponse(**product_dict))

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
    colors, price range. Used by the React FilterSidebar to populate
    dropdowns/checkboxes.
    """
    cat_rows = (await db.execute(
        select(Product.category).distinct()
    )).scalars().all()
    color_rows = (await db.execute(
        select(Product.color).distinct().where(Product.color.isnot(None))
    )).scalars().all()
    price_row = (await db.execute(
        select(func.min(Product.price), func.max(Product.price))
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
    # Pull canonical list from the categories table; counts and subcategories
    # come from products. Categories without products show count=0.
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
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Check if favorite
    is_favorite = False
    if current_user:
        fav_result = await db.execute(
            select(Favorite).where(
                Favorite.user_id == current_user.id,
                Favorite.product_id == product_id
            )
        )
        is_favorite = fav_result.scalar_one_or_none() is not None

    return ProductResponse(
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
        model_glb_url=product.model_glb_url,
        model_usdz_url=product.model_usdz_url,
        created_at=product.created_at,
        is_favorite=is_favorite
    )
