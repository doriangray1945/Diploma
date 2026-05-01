from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=True)


async def init_pgvector():
    """Enable pgvector extension in PostgreSQL."""
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


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
