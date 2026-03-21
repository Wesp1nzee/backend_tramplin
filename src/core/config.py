from typing import Literal

from pydantic import PostgresDsn, RedisDsn, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True
    )

    PROJECT_NAME: str = "Tramplin API"
    ENVIRONMENT: Literal["dev", "prod", "test"] = "dev"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 30

    # --- CORS ---
    CORS_ORIGINS: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        """Возвращает распарсенный список CORS-оригинов"""
        if not self.CORS_ORIGINS or not self.CORS_ORIGINS.strip():
            return ["http://localhost:3000"]

        origins = [
            origin.strip().rstrip("/") for origin in self.CORS_ORIGINS.split(",") if origin.strip()
        ]
        return origins if origins else ["http://localhost:3000"]

    # --- Infrastructure ---
    POSTGRES_SERVER: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    DATABASE_URL: PostgresDsn | None = None

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: str | None, values: ValidationInfo) -> str:
        if isinstance(v, str) and v:
            return v
        return str(
            PostgresDsn.build(
                scheme="postgresql+asyncpg",
                username=values.data.get("POSTGRES_USER"),
                password=values.data.get("POSTGRES_PASSWORD"),
                host=values.data.get("POSTGRES_SERVER"),
                path=values.data.get("POSTGRES_DB") or "",
            )
        )

    # Valkey (Redis-compatible)
    VALKEY_URL: RedisDsn

    # RabbitMQ
    RABBITMQ_URL: str = "amqp://guest:guest@mq:5672/"

    # --- Business Logic Defaults ---
    MIN_PASSWORD_LENGTH: int = 8
    MAX_IMAGE_SIZE_MB: int = 5


settings = Settings()
