from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=True)


async def init_pgvector():
    """Enable pgvector + pg_search extensions in PostgreSQL.

    pgvector: used by plan_cache for semantic plan retrieval and (still
        present, currently dormant) by Product.embedding.
    pg_search: BM25 full-text search engine (ParadeDB / Tantivy) used for
        the catalog search UI and the apply_filters chat tool.
    """
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_search"))


async def apply_inline_migrations():
    """Idempotent ALTERs for columns added to pre-existing tables.

    SQLAlchemy's `Base.metadata.create_all` only creates missing tables,
    not missing columns. We don't run Alembic; additive migrations live
    here as `ADD COLUMN IF NOT EXISTS`. Each statement must be idempotent.
    """
    async with engine.begin() as conn:
        await conn.execute(text(
            "ALTER TABLE chat_sessions "
            "ADD COLUMN IF NOT EXISTS last_cache_hit_id INTEGER"
        ))
        await conn.execute(text(
            "ALTER TABLE users "
            "ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE"
        ))
        await conn.execute(text(
            "ALTER TABLE users "
            "ADD COLUMN IF NOT EXISTS is_superadmin BOOLEAN NOT NULL DEFAULT FALSE"
        ))
        # 3D model URLs migrated from product to variant level so each colour/
        # size can carry its own GLB. ADD on variants first (idempotent), then
        # DROP on products (also idempotent — IF EXISTS).
        await conn.execute(text(
            "ALTER TABLE product_variants ADD COLUMN IF NOT EXISTS model_glb_url VARCHAR(500)"
        ))
        await conn.execute(text(
            "ALTER TABLE product_variants ADD COLUMN IF NOT EXISTS model_usdz_url VARCHAR(500)"
        ))
        await conn.execute(text(
            "ALTER TABLE products DROP COLUMN IF EXISTS model_glb_url"
        ))
        await conn.execute(text(
            "ALTER TABLE products DROP COLUMN IF EXISTS model_usdz_url"
        ))
        # Track which SKU was bought so analytics can group_by color/size.
        # SET NULL on variant delete keeps order history intact.
        await conn.execute(text(
            "ALTER TABLE order_items "
            "ADD COLUMN IF NOT EXISTS variant_id INTEGER "
            "REFERENCES product_variants(id) ON DELETE SET NULL"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_order_items_variant_id "
            "ON order_items (variant_id)"
        ))
        # Switch from nomic-embed-text (dim=768) to bge-m3 (dim=1024). Old
        # vectors are incompatible after model swap. Run the destructive
        # ALTER ... USING NULL only when the column is still at 768; once
        # bumped to 1024 the block becomes a no-op so subsequent restarts
        # don't wipe re-computed embeddings.
        await conn.execute(text("""
            DO $do$
            DECLARE current_dim integer;
            BEGIN
                SELECT atttypmod INTO current_dim FROM pg_attribute
                WHERE attrelid = 'products'::regclass AND attname = 'embedding';
                IF current_dim IS NOT NULL AND current_dim <> 1024 THEN
                    ALTER TABLE products ALTER COLUMN embedding TYPE vector(1024) USING NULL;
                END IF;
                SELECT atttypmod INTO current_dim FROM pg_attribute
                WHERE attrelid = 'plan_cache_entries'::regclass AND attname = 'query_embedding';
                IF current_dim IS NOT NULL AND current_dim <> 1024 THEN
                    ALTER TABLE plan_cache_entries ALTER COLUMN query_embedding TYPE vector(1024)
                        USING ARRAY_FILL(0::real, ARRAY[1024])::vector;
                    DELETE FROM plan_cache_entries;
                END IF;
            END $do$;
        """))
        # BM25 full-text index over searchable product fields. pg_search
        # builds a Tantivy index covering name + description + category +
        # subcategory + materials + color, with the Snowball Russian
        # stemmer applied to each — so «офисный»/«офисное», «детская»/
        # «детский», «кожаный»/«кожаное» collapse to one stem in both
        # the index and the query, and `apply_search_filter` can rank
        # any inflected form. Queried via the `field @@@ 'text'` operator
        # and ranked by `paradedb.score(id) DESC`. Idempotent.
        # `color` moved to product_variants and was removed from products.
        # Drop any stale BM25 index that references it before recreating
        # without the column.
        await conn.execute(text("DROP INDEX IF EXISTS products_bm25_idx"))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS products_bm25_idx ON products
            USING bm25 (id, name, description, category, subcategory, materials)
            WITH (
                key_field = 'id',
                text_fields = '{
                    "name":        {"tokenizer": {"type": "default", "stemmer": "Russian"}},
                    "description": {"tokenizer": {"type": "default", "stemmer": "Russian"}},
                    "category":    {"tokenizer": {"type": "default", "stemmer": "Russian"}},
                    "subcategory": {"tokenizer": {"type": "default", "stemmer": "Russian"}},
                    "materials":   {"tokenizer": {"type": "default", "stemmer": "Russian"}}
                }'
            )
        """))
        # Bootstrap categories table from distinct product.category values so
        # the catalog stays unchanged for users while the admin panel gains a
        # canonical, editable list. Idempotent.
        result = await conn.execute(text("SELECT COUNT(*) FROM categories"))
        if result.scalar_one() == 0:
            await conn.execute(text(
                "INSERT INTO categories (name, sort_order, created_at) "
                "SELECT DISTINCT category, 0, NOW() FROM products "
                "WHERE category IS NOT NULL "
                "ON CONFLICT (name) DO NOTHING"
            ))
        # Reviews table — one row per (user, product) thanks to UNIQUE.
        # Product.rating and Product.reviews_count are recomputed by the
        # reviews route on every CRUD operation; a backfill run on the next
        # restart will recompute existing rows from any seeded reviews.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS reviews (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
                text VARCHAR(2000),
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_review_user_product UNIQUE (user_id, product_id)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_reviews_product_id ON reviews(product_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_reviews_user_id ON reviews(user_id)"
        ))

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
