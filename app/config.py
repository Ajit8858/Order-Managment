from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "Order Management Backend"
    ENV: str = "development"
    API_V1_PREFIX: str = "/api/v1"

    SECRET_KEY: str = "dev-secret-key-change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    DATABASE_URL: str = "postgresql+asyncpg://omb_user:omb_pass@localhost:5432/order_management"
    SYNC_DATABASE_URL: str = "postgresql+psycopg2://omb_user:omb_pass@localhost:5432/order_management"

    REDIS_URL: str = "redis://localhost:6379/0"

    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    EMAIL_ENABLED: bool = False
    SMTP_HOST: str = "smtp.mailtrap.io"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = "orders@example.com"

    RATE_LIMIT_PER_MINUTE: int = 60

    PRODUCT_CACHE_TTL_SECONDS: int = 300


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
