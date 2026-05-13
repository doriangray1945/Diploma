import logging
import re
from decimal import Decimal

from sqlalchemy import case, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.services.semantics import resolve_price_level
from app.models import Product, ProductVariant
from app.schemas.admin import AdminFilter


log = logging.getLogger(__name__)


_BM25_FIELDS = ("name", "description", "category", "subcategory", "materials")


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
    # Sanitize: Tantivy treats characters like <, >, +, -, !, (), [], {}, ", ~,
    # *, ?, :, \, ^, &, | as query syntax. Raw user input containing them (e.g.
    # «<script>», «foo:bar», «'; DROP» → trailing «--») triggers a parse error
    # → 500. Strip everything except letters (any Unicode), digits, whitespace.
    text_value = re.sub(r"[^\w\s]", " ", search).strip()
    if not text_value:
        return query
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
    """Translate AdminFilter into SQLAlchemy WHERE clauses on ProductVariant.

    Returns a query that selects matching `ProductVariant` rows. Variant-level
    criteria (color, price, in_stock, price_level, product_ids) filter
    variants directly. Product-level criteria (category, material,
    product_name, search) join through Product.

    Industry-standard SKU semantics: filtering by color updates only that
    colour's variants, not all variants of products that have that colour.
    """
    if flt.product_ids:
        query = query.where(ProductVariant.product_id.in_(flt.product_ids))

    # Variant-level fields
    if flt.color:
        query = query.where(ProductVariant.color.in_(flt.color))
    if flt.min_price is not None:
        query = query.where(ProductVariant.price >= flt.min_price)
    if flt.max_price is not None:
        query = query.where(ProductVariant.price <= flt.max_price)
    if flt.price_level:
        lvl_min, lvl_max = resolve_price_level(flt.price_level)
        if lvl_min is not None:
            query = query.where(ProductVariant.price >= lvl_min)
        if lvl_max is not None:
            query = query.where(ProductVariant.price <= lvl_max)
    if flt.in_stock is not None:
        query = query.where(ProductVariant.in_stock == flt.in_stock)

    # Product-level fields — JOIN once if any of them are set.
    needs_product_join = bool(
        flt.category or flt.material or flt.product_name or flt.search
    )
    if needs_product_join:
        query = query.join(Product, Product.id == ProductVariant.product_id)
        if flt.category:
            query = query.where(Product.category == flt.category)
        if flt.material:
            from app.services.semantics import resolve_material
            substrings: list[str] = []
            for m in flt.material:
                substrings.extend(resolve_material(m) or [m])
            if substrings:
                query = query.where(or_(*[Product.materials.ilike(f"%{s}%") for s in substrings]))
        if flt.product_name:
            query = query.where(Product.name.ilike(f"%{flt.product_name}%"))
        if flt.search:
            query = apply_search_filter(query, flt.search)
    return query


async def bulk_update_stock(
    db: AsyncSession, flt: AdminFilter, operation: str, quantity: int
) -> int:
    """Bulk-update stock_quantity on matching ProductVariant rows.
    Returns affected variant count.

    operation:
      - "set"      → SET stock_quantity = quantity
      - "add"      → SET stock_quantity = stock_quantity + quantity
      - "subtract" → SET stock_quantity = GREATEST(0, stock_quantity - quantity)
    """
    base = _apply_admin_filter(select(ProductVariant.id), flt)
    matching = (await db.execute(base)).scalars().all()
    if not matching:
        return 0

    if operation == "set":
        new_qty = quantity
    elif operation == "add":
        new_qty = ProductVariant.stock_quantity + quantity
    elif operation == "subtract":
        new_qty = case(
            (ProductVariant.stock_quantity - quantity < 0, 0),
            else_=ProductVariant.stock_quantity - quantity,
        )
    else:
        raise ValueError(f"unknown stock operation: {operation}")

    await db.execute(
        update(ProductVariant)
        .where(ProductVariant.id.in_(matching))
        .values(stock_quantity=new_qty)
    )

    # Sync in_stock = (stock_quantity > 0) — second pass after mutation.
    await db.execute(
        update(ProductVariant)
        .where(ProductVariant.id.in_(matching))
        .values(in_stock=(ProductVariant.stock_quantity > 0))
    )
    await db.commit()
    return len(matching)


async def bulk_update_prices(
    db: AsyncSession, flt: AdminFilter, operation: str, value: int
) -> tuple[int, Decimal]:
    """Bulk-update prices on matching ProductVariant rows.
    Returns (affected_variant_count, total_revenue_delta).

    Saves current price into variant.old_price (if not already set) so UI
    can show "old price crossed out" for discounted SKUs.
    """
    base = _apply_admin_filter(select(ProductVariant.id, ProductVariant.price), flt)
    rows = (await db.execute(base)).all()
    if not rows:
        return (0, Decimal("0"))

    matching_ids = [r.id for r in rows]
    old_total = sum((Decimal(str(r.price)) for r in rows), Decimal("0"))

    # Reset: «убери скидки» — восстановить price из old_price.
    # Триггерится либо явной операцией "reset", либо discount=0 (модель
    # часто описывает «убрать скидку» именно как «discount 0%»).
    is_reset = operation == "reset" or (operation == "discount" and value == 0)

    if is_reset:
        # price := old_price (где old_price задан), затем очистить old_price
        await db.execute(
            update(ProductVariant)
            .where(
                ProductVariant.id.in_(matching_ids),
                ProductVariant.old_price.is_not(None),
            )
            .values(price=ProductVariant.old_price, old_price=None)
        )
        await db.commit()
        new_rows = (await db.execute(
            select(ProductVariant.price).where(ProductVariant.id.in_(matching_ids))
        )).all()
        new_total = sum((Decimal(str(r.price)) for r in new_rows), Decimal("0"))
        return (len(matching_ids), new_total - old_total)

    if operation == "discount":
        factor = Decimal("1") - Decimal(value) / Decimal("100")
        new_price_expr = ProductVariant.price * float(factor)
    elif operation == "markup":
        factor = Decimal("1") + Decimal(value) / Decimal("100")
        new_price_expr = ProductVariant.price * float(factor)
    elif operation == "set_price":
        new_price_expr = float(value)
    else:
        raise ValueError(f"unknown price operation: {operation}")

    # Save old_price snapshot before mutation (only for variants without one).
    await db.execute(
        update(ProductVariant)
        .where(ProductVariant.id.in_(matching_ids), ProductVariant.old_price.is_(None))
        .values(old_price=ProductVariant.price)
    )

    await db.execute(
        update(ProductVariant)
        .where(ProductVariant.id.in_(matching_ids))
        .values(price=new_price_expr)
    )
    await db.commit()

    new_rows = (await db.execute(
        select(ProductVariant.price).where(ProductVariant.id.in_(matching_ids))
    )).all()
    new_total = sum((Decimal(str(r.price)) for r in new_rows), Decimal("0"))
    return (len(matching_ids), new_total - old_total)
