from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    PROJECT_NAME: str = "Furniture Store API"
    VERSION: str = "1.0.0"
    API_PREFIX: str = "/api"

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/furniture_store"

    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    OLLAMA_HOST: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen3:8b"

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
