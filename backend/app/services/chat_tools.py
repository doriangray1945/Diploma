from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload

from app.models import Product, CartItem, Order, OrderItem, User


async def execute_tool(
    tool_name: str,
    arguments: dict,
    db: AsyncSession,
    user: User
) -> dict:
    """Execute a tool call and return the result."""

    if tool_name == "search_products":
        return await search_products(db, user, **arguments)
    elif tool_name == "get_product_details":
        return await get_product_details(db, **arguments)
    elif tool_name == "apply_filters":
        return {"action": "apply_filters", "filters": arguments}
    elif tool_name == "add_to_cart":
        return await add_to_cart(db, user, **arguments)
    elif tool_name == "get_cart":
        return await get_cart(db, user)
    elif tool_name == "create_order":
        return await create_order(db, user, **arguments)
    else:
        return {"error": f"Unknown tool: {tool_name}"}


async def search_products(
    db: AsyncSession,
    user: User,
    query: str | None = None,
    category: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    color: str | None = None,
    limit: int = 5
) -> dict:
    """Search products with filters."""
    q = select(Product)

    if query:
        search_pattern = f"%{query}%"
        q = q.where(
            or_(
                Product.name.ilike(search_pattern),
                Product.description.ilike(search_pattern)
            )
        )

    if category:
        q = q.where(Product.category.ilike(f"%{category}%"))

    if min_price is not None:
        q = q.where(Product.price >= min_price)

    if max_price is not None:
        q = q.where(Product.price <= max_price)

    if color:
        q = q.where(Product.color.ilike(f"%{color}%"))

    q = q.where(Product.in_stock == True).limit(limit)

    result = await db.execute(q)
    products = result.scalars().all()

    return {
        "action": "show_products",
        "products": [
            {
                "id": p.id,
                "name": p.name,
                "price": float(p.price),
                "category": p.category,
                "color": p.color,
                "dimensions": p.dimensions,
                "in_stock": p.in_stock,
                "description": p.description[:200] + "..." if len(p.description) > 200 else p.description
            }
            for p in products
        ],
        "count": len(products)
    }


async def get_product_details(db: AsyncSession, product_id: int) -> dict:
    """Get detailed product information."""
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()

    if not product:
        return {"error": "Товар не найден"}

    return {
        "action": "show_product_details",
        "product": {
            "id": product.id,
            "name": product.name,
            "description": product.description,
            "price": float(product.price),
            "old_price": float(product.old_price) if product.old_price else None,
            "category": product.category,
            "dimensions": product.dimensions,
            "materials": product.materials,
            "color": product.color,
            "in_stock": product.in_stock,
            "stock_quantity": product.stock_quantity,
            "rating": float(product.rating),
            "reviews_count": product.reviews_count
        }
    }


async def add_to_cart(
    db: AsyncSession,
    user: User,
    product_id: int,
    quantity: int = 1
) -> dict:
    """Add product to user's cart."""
    # Check product exists
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()

    if not product:
        return {"error": "Товар не найден"}

    if not product.in_stock:
        return {"error": "Товар не в наличии"}

    # Check if already in cart
    cart_result = await db.execute(
        select(CartItem).where(
            CartItem.user_id == user.id,
            CartItem.product_id == product_id
        )
    )
    existing = cart_result.scalar_one_or_none()

    if existing:
        existing.quantity += quantity
    else:
        cart_item = CartItem(
            user_id=user.id,
            product_id=product_id,
            quantity=quantity
        )
        db.add(cart_item)

    await db.commit()

    return {
        "action": "added_to_cart",
        "product_name": product.name,
        "quantity": quantity,
        "price": float(product.price)
    }


async def get_cart(db: AsyncSession, user: User) -> dict:
    """Get user's cart contents."""
    result = await db.execute(
        select(CartItem)
        .where(CartItem.user_id == user.id)
        .options(selectinload(CartItem.product))
    )
    items = result.scalars().all()

    total = 0.0
    cart_items = []
    for item in items:
        item_total = float(item.product.price) * item.quantity
        total += item_total
        cart_items.append({
            "id": item.id,
            "product_id": item.product_id,
            "product_name": item.product.name,
            "quantity": item.quantity,
            "price": float(item.product.price),
            "subtotal": item_total
        })

    return {
        "action": "show_cart",
        "items": cart_items,
        "total": round(total, 2),
        "items_count": len(cart_items)
    }


async def create_order(
    db: AsyncSession,
    user: User,
    address: str,
    phone: str
) -> dict:
    """Create an order from cart."""
    # Get cart
    cart_result = await db.execute(
        select(CartItem)
        .where(CartItem.user_id == user.id)
        .options(selectinload(CartItem.product))
    )
    cart_items = cart_result.scalars().all()

    if not cart_items:
        return {"error": "Корзина пуста"}

    # Calculate total
    total = 0.0
    order_items = []
    for item in cart_items:
        item_total = float(item.product.price) * item.quantity
        total += item_total
        order_items.append(OrderItem(
            product_id=item.product_id,
            product_name=item.product.name,
            quantity=item.quantity,
            price=float(item.product.price)
        ))

    # Create order
    order = Order(
        user_id=user.id,
        status="pending",
        total=total,
        address=address,
        phone=phone
    )
    db.add(order)
    await db.flush()

    # Add items
    for item in order_items:
        item.order_id = order.id
        db.add(item)

    # Clear cart
    for cart_item in cart_items:
        await db.delete(cart_item)

    await db.commit()

    return {
        "action": "order_created",
        "order_id": order.id,
        "total": round(total, 2),
        "status": "pending",
        "message": f"Заказ №{order.id} успешно создан! Сумма: {total:.2f} руб."
    }
