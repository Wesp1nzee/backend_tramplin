import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from src.models.user import UserRole


# Общая настройка для всех схем (позволяет работать с ORM моделями)
class SchemaBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Входные данные (Request) ---


class UserCreate(SchemaBase):
    """Схема для регистрации нового пользователя."""

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    role: UserRole = UserRole.APPLICANT
    first_name: str = Field(..., min_length=2, max_length=100)
    last_name: str = Field(..., min_length=2, max_length=100)


class UserUpdate(SchemaBase):
    """Схема для частичного обновления профиля (PATCH)."""

    first_name: str | None = None
    last_name: str | None = None
    university: str | None = None
    graduation_year: int | None = Field(None, ge=2000, le=2100)
    skills: list[str] | None = None
    github_url: str | None = None
    privacy_settings: dict[str, bool] | None = None

    @field_validator("github_url")
    @classmethod
    def validate_github_url(cls, v: str | None) -> str | None:
        if v and "github.com" not in v:
            raise ValueError("Ссылка должна вести на github.com")
        return v


# --- Выходные данные (Response) ---


class ProfileResponse(SchemaBase):
    """Данные профиля, которые возвращаются клиенту."""

    first_name: str
    last_name: str
    middle_name: str | None
    university: str | None
    graduation_year: int | None
    skills: list[str]
    github_url: str | None
    privacy_settings: dict[str, Any]


class UserResponse(SchemaBase):
    """Полный объект пользователя для API."""

    id: uuid.UUID
    email: EmailStr
    role: UserRole
    is_verified: bool
    created_at: datetime
    profile: ProfileResponse | None

class TokenResponse(BaseModel):
    """Схема ответа с токенами доступа."""

    access_token: str = Field(..., description="JWT токен доступа")
    refresh_token: str = Field(..., description="JWT токен обновления")
    token_type: str = Field(default="bearer", description="Тип токена")

    class Config:
        from_attributes = True