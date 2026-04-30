import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import engine, Base, init_pgvector, apply_inline_migrations
from app.api.routes import api_router


# Surface [CACHE]/[TOOL]/[LLM] logs from `core.*` modules. Without this they
# get filtered by uvicorn's default logger config.
logging.basicConfig(level=logging.INFO)
logging.getLogger("core").setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: pgvector extension, table creation, additive column migrations
    await init_pgvector()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await apply_inline_migrations()
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
