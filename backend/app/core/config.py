from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    PROJECT_NAME: str = "Furniture Store API"
    VERSION: str = "1.0.0"
    API_PREFIX: str = "/api"

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/furniture_store"

    SECRET_KEY: str  # required — must be set in .env, no default
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    OLLAMA_HOST: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:3b"

    # Seeded admin account (out-of-band privilege grant). If both are set and
    # the user does not yet exist, lifespan creates them with is_admin=True.
    ADMIN_EMAIL: str | None = None
    ADMIN_PASSWORD: str | None = None

    # MinIO S3 object storage. Bucket holds catalog product images.
    # MINIO_ENDPOINT is the in-network address used by backend (e.g. compose service name).
    # MINIO_PUBLIC_ENDPOINT is what gets stored in DB/served to browsers.
    MINIO_ENDPOINT: str = "http://localhost:9000"
    MINIO_PUBLIC_ENDPOINT: str = "http://localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin123"
    MINIO_BUCKET: str = "furniture-images"

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
