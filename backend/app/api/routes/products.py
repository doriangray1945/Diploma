from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_

from app.core.database import get_db
from app.models import Product, Favorite, User, Category
from app.schemas import ProductResponse, ProductListResponse, CategoryResponse
from app.api.deps import get_current_user_optional

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
    color: str | None = None,
    in_stock: bool | None = None,
    is_popular: bool | None = None,
    is_new: bool | None = None,
    search: str | None = None,
    sort_by: str = Query("created_at", pattern="^(created_at|price|rating|name)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$")
):
    # Build query
    query = select(Product)

    # Apply filters
    if category:
        query = query.where(Product.category == category)
    if subcategory:
        query = query.where(Product.subcategory == subcategory)
    if min_price is not None:
        query = query.where(Product.price >= min_price)
    if max_price is not None:
        query = query.where(Product.price <= max_price)
    if color:
        query = query.where(Product.color == color)
    if in_stock is not None:
        query = query.where(Product.in_stock == in_stock)
    if is_popular is not None:
        query = query.where(Product.is_popular == is_popular)
    if is_new is not None:
        query = query.where(Product.is_new == is_new)
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            or_(
                Product.name.ilike(search_pattern),
                Product.description.ilike(search_pattern)
            )
        )

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply sorting
    sort_column = getattr(Product, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    # Apply pagination
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
        pages=pages
    )


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
        created_at=product.created_at,
        is_favorite=is_favorite
    )
