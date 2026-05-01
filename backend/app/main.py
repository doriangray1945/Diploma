import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.core.config import settings
from app.core.database import engine, Base, init_pgvector, apply_inline_migrations, async_session_maker
from app.core.security import get_password_hash
from app.models import User
from app.api.routes import api_router


# Surface [CACHE]/[TOOL]/[LLM] logs from `core.*` modules. Without this they
# get filtered by uvicorn's default logger config.
logging.basicConfig(level=logging.INFO)
logging.getLogger("core").setLevel(logging.INFO)

log = logging.getLogger(__name__)


async def seed_admin() -> None:
    """Ensure the seeded super-admin account exists with full privileges.

    The super-admin role is granted *only* through this env-driven seed —
    never via the public API or another admin. If the configured user is
    missing it gets created; if present but not yet flagged as super-admin
    (e.g. legacy data), it gets upgraded in place. Idempotent.
    """
    if not settings.ADMIN_EMAIL or not settings.ADMIN_PASSWORD:
        return
    async with async_session_maker() as db:
        existing = (
            await db.execute(select(User).where(User.email == settings.ADMIN_EMAIL))
        ).scalar_one_or_none()
        if existing is not None:
            changed = False
            if not existing.is_admin:
                existing.is_admin = True
                changed = True
            if not existing.is_superadmin:
                existing.is_superadmin = True
                changed = True
            if changed:
                await db.commit()
                log.info("[SEED] upgraded existing user to super-admin: %s", settings.ADMIN_EMAIL)
            else:
                log.info("[SEED] super-admin user %s already exists", settings.ADMIN_EMAIL)
            return
        admin = User(
            email=settings.ADMIN_EMAIL,
            name="Administrator",
            password_hash=get_password_hash(settings.ADMIN_PASSWORD),
            is_admin=True,
            is_superadmin=True,
        )
        db.add(admin)
        await db.commit()
        log.info("[SEED] super-admin user created: %s", settings.ADMIN_EMAIL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: pgvector extension, table creation, additive column migrations
    await init_pgvector()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await apply_inline_migrations()
    await seed_admin()
    yield
    # Shutdown
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router, prefix=settings.API_PREFIX)


@app.get("/")
async def root():
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
