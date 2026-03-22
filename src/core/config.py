from typing import Literal

from pydantic import Field, PostgresDsn, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=True
    )

    PROJECT_NAME: str = "Tramplin API"
    ENVIRONMENT: Literal["dev", "prod", "test"] = "dev"
    DEBUG: bool = True
    ENABLE_DOCS: bool = False
    ENABLE_RATE_LIMITING: bool = True
    API_V1_STR: str = "/api/v1"

    SECRET_KEY: str = Field(..., description="Секретный ключ для JWT (минимум 32 символа)")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15  # 15 минут
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 дней

    DEFAULT_ADMIN_EMAIL: str = Field(
        default="admin@tramplin.ru", description="Email администратора по умолчанию"
    )
    DEFAULT_ADMIN_PASSWORD: str = Field(
        ..., description="Пароль администратора по умолчанию (требуется в prod)"
    )

    CORS_ORIGINS: str = ""

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long")
        if v == "dev_secret_key_change_me_in_prod":
            raise ValueError("SECRET_KEY must be changed from default value")
        if v.startswith("dev_") or v.endswith("_dev"):
            raise ValueError("SECRET_KEY should not contain dev markers in production")
        return v

    @field_validator("DEFAULT_ADMIN_PASSWORD")
    @classmethod
    def validate_admin_password(cls, v: str) -> str:
        if len(v) < 12:
            raise ValueError("Admin password must be at least 12 characters")
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        """Возвращает распарсенный список CORS-оригинов"""
        if not self.CORS_ORIGINS or not self.CORS_ORIGINS.strip():
            return ["http://localhost:3000"]

        origins = [
            origin.strip().rstrip("/") for origin in self.CORS_ORIGINS.split(",") if origin.strip()
        ]
        return origins if origins else ["http://localhost:3000"]

    POSTGRES_SERVER: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    DATABASE_URL: str | PostgresDsn

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: str | None, values: ValidationInfo) -> str:
        if isinstance(v, str) and v:
            return v

        user = values.data.get("POSTGRES_USER")
        password = values.data.get("POSTGRES_PASSWORD")
        server = values.data.get("POSTGRES_SERVER")

        if not all([user, password, server]):
            return "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"

        return str(
            PostgresDsn.build(
                scheme="postgresql+asyncpg",
                username=values.data.get("POSTGRES_USER"),
                password=values.data.get("POSTGRES_PASSWORD"),
                host=values.data.get("POSTGRES_SERVER"),
                path=values.data.get("POSTGRES_DB") or "",
            )
        )

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    # RabbitMQ
    RABBITMQ_URL: str = "amqp://guest:guest@mq:5672/"

    # --- Business Logic Defaults ---
    MIN_PASSWORD_LENGTH: int = 8
    MAX_IMAGE_SIZE_MB: int = 5


settings = Settings()
