import logging
from decimal import Decimal

from sqlalchemy import or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.core.semantic_config import resolve_price_level
from app.models import Product
from app.schemas.admin import AdminFilter


log = logging.getLogger(__name__)


def build_product_text(product: Product) -> str:
    """Searchable text used to compute the (legacy) product embedding.

    Kept for the dormant `Product.embedding` column — admin CRUD still
    populates it on save in case we ever want a hybrid lexical+vector
    search later. The active search path is BM25 over the same fields,
    via `apply_search_filter`.
    """
    parts = [product.name, product.description or "", product.category or ""]
    if product.subcategory:
        parts.append(product.subcategory)
    if product.color:
        parts.append(f"цвет: {product.color}")
    if product.materials:
        parts.append(f"материалы: {product.materials}")
    return " ".join(parts)


# Fields that, when changed, require recomputing the embedding. Other fields
# (price, stock, dimensions, flags) don't affect semantic search results.
EMBEDDING_FIELDS = frozenset({"name", "description", "category", "subcategory", "materials", "color"})


_BM25_FIELDS = ("name", "description", "category", "subcategory", "materials", "color")


def apply_search_filter(query: Select, search: str | None) -> Select:
    """Apply BM25 full-text search to a Product `select()` query.

    Uses the `pg_search` (ParadeDB) extension. The index is built with
    a Snowball Russian stemmer (see `apply_inline_migrations`), which
    means «офисный»/«офисное», «детская»/«детский», «кожаный»/«кожаное»
    all collapse to the same stem in both the index and the query. So
    a plain `field @@@ 'token'` just works for any inflected form.

    Tantivy parses `column @@@ 'text'` as a query against `column`, so
    to search «across all indexed text fields» we OR the operator over
    each one — pg_search's BM25 scoring sums the per-field contributions
    automatically. Results are ordered by `paradedb.score(id) DESC`.

    On empty/blank search returns the query unchanged. No threshold, no
    «show-everything» fallback — BM25 returns matches in order of
    relevance, and zero matches means the answer really is «nothing
    matches that query».
    """
    if not search or not search.strip():
        return query
    text_value = search.strip()
    or_clauses = " OR ".join(
        f"products.{f} @@@ :search_q" for f in _BM25_FIELDS
    )
    return (
        query
        .where(text(f"({or_clauses})").bindparams(search_q=text_value))
        .order_by(text("paradedb.score(products.id) DESC"))
    )


# ---------------------------------------------------------------------------
# Bulk admin operations — translate AdminFilter → WHERE clauses, run UPDATE
# ---------------------------------------------------------------------------

def _apply_admin_filter(query: Select, flt: AdminFilter) -> Select:
    """Translate AdminFilter into SQLAlchemy WHERE clauses.

    Mirrors the semantics of the chat tool's apply_filters but operates
    over Product directly. Used by both bulk operations and analytics.
    """
    if flt.product_ids:
        return query.where(Product.id.in_(flt.product_ids))

    if flt.category:
        query = query.where(Product.category == flt.category)
    if flt.color:
        query = query.where(Product.color.in_(flt.color))
    if flt.material:
        from app.core.semantic_config import resolve_material
        substrings: list[str] = []
        for m in flt.material:
            substrings.extend(resolve_material(m) or [m])
        if substrings:
            query = query.where(or_(*[Product.materials.ilike(f"%{s}%") for s in substrings]))
    if flt.price_level:
        lvl_min, lvl_max = resolve_price_level(flt.price_level)
        if lvl_min is not None:
            query = query.where(Product.price >= lvl_min)
        if lvl_max is not None:
            query = query.where(Product.price <= lvl_max)
    if flt.min_price is not None:
        query = query.where(Product.price >= flt.min_price)
    if flt.max_price is not None:
        query = query.where(Product.price <= flt.max_price)
    if flt.in_stock is not None:
        query = query.where(Product.in_stock == flt.in_stock)
    if flt.product_name:
        query = query.where(Product.name.ilike(f"%{flt.product_name}%"))
    if flt.search:
        query = apply_search_filter(query, flt.search)
    return query


async def bulk_update_stock(
    db: AsyncSession, flt: AdminFilter, operation: str, quantity: int
) -> int:
    """Bulk-update stock_quantity for matching products. Returns affected count.

    operation:
      - "set"      → SET stock_quantity = quantity
      - "add"      → SET stock_quantity = stock_quantity + quantity
      - "subtract" → SET stock_quantity = GREATEST(0, stock_quantity - quantity)
    """
    base = _apply_admin_filter(select(Product.id), flt)
    matching = (await db.execute(base)).scalars().all()
    if not matching:
        return 0

    if operation == "set":
        new_qty = quantity
    elif operation == "add":
        new_qty = Product.stock_quantity + quantity
    elif operation == "subtract":
        from sqlalchemy import case
        new_qty = case(
            (Product.stock_quantity - quantity < 0, 0),
            else_=Product.stock_quantity - quantity,
        )
    else:
        raise ValueError(f"unknown stock operation: {operation}")

    stmt = (
        update(Product)
        .where(Product.id.in_(matching))
        .values(stock_quantity=new_qty)
    )
    await db.execute(stmt)

    # Sync in_stock = (stock_quantity > 0) — second pass needed because
    # we just changed stock_quantity in step above.
    sync_stmt = (
        update(Product)
        .where(Product.id.in_(matching))
        .values(in_stock=(Product.stock_quantity > 0))
    )
    await db.execute(sync_stmt)
    await db.commit()
    return len(matching)


async def bulk_update_prices(
    db: AsyncSession, flt: AdminFilter, operation: str, value: int
) -> tuple[int, Decimal]:
    """Bulk-update prices. Returns (affected_count, total_revenue_delta).

    Saves current price into old_price (if not already set) so UI can
    show "old price crossed out" for discounted items.
    """
    base = _apply_admin_filter(select(Product.id, Product.price), flt)
    rows = (await db.execute(base)).all()
    if not rows:
        return (0, Decimal("0"))

    matching_ids = [r.id for r in rows]
    old_total = sum((Decimal(str(r.price)) for r in rows), Decimal("0"))

    if operation == "discount":
        # SET price = ROUND(price * (1 - value/100), 0)
        factor = Decimal("1") - Decimal(value) / Decimal("100")
        new_price_expr = Product.price * float(factor)
    elif operation == "markup":
        factor = Decimal("1") + Decimal(value) / Decimal("100")
        new_price_expr = Product.price * float(factor)
    elif operation == "set_price":
        new_price_expr = float(value)
    else:
        raise ValueError(f"unknown price operation: {operation}")

    # Save old_price snapshot before mutation (only for items that don't have one).
    save_old = (
        update(Product)
        .where(Product.id.in_(matching_ids), Product.old_price.is_(None))
        .values(old_price=Product.price)
    )
    await db.execute(save_old)

    stmt = (
        update(Product)
        .where(Product.id.in_(matching_ids))
        .values(price=new_price_expr)
    )
    await db.execute(stmt)
    await db.commit()

    # Compute revenue impact: total of new prices minus total of old.
    new_rows = (await db.execute(
        select(Product.price).where(Product.id.in_(matching_ids))
    )).all()
    new_total = sum((Decimal(str(r.price)) for r in new_rows), Decimal("0"))
    return (len(matching_ids), new_total - old_total)
