import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from src.models.enums import UserRole


class SchemaBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserCreate(SchemaBase):
    """Схема для регистрации нового пользователя."""

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    role: UserRole = UserRole.APPLICANT
    first_name: str = Field(..., min_length=2, max_length=100)
    last_name: str = Field(..., min_length=2, max_length=100)


class UserUpdate(SchemaBase):
    """Схема для PATCH."""

    first_name: str | None = None
    last_name: str | None = None
    university: str | None = None
    graduation_year: int | None = Field(None, ge=2000, le=2100)
    skills: list[str] | None = None
    social_links: dict[str, str] | None = None
    privacy_settings: dict[str, bool] | None = None


class ProfileResponse(SchemaBase):
    """Данные профиля для клиента."""

    first_name: str
    last_name: str
    middle_name: str | None = None
    university: str | None = None
    graduation_year: int | None = None
    skills: list[str] = []
    social_links: dict[str, str] = {}
    privacy_settings: dict[str, Any] = {}


class UserResponse(SchemaBase):
    """Полный объект пользователя для API."""

    id: uuid.UUID
    email: EmailStr
    role: UserRole
    is_verified: bool
    created_at: datetime
    profile: ProfileResponse | None


class TokenResponse(SchemaBase):
    """Схема ответа только с токенами (используется в /refresh)."""

    access_token: str = Field(..., description="JWT токен доступа")
    refresh_token: str = Field(..., description="JWT токен обновления")
    token_type: str = Field(default="bearer", description="Тип токена")


class AuthResponse(SchemaBase):
    """
    Единый ответ для /register и /login.
    Возвращает токены + данные пользователя, чтобы фронту
    не требовался дополнительный запрос GET /users/me.
    """

    access_token: str = Field(..., description="JWT токен доступа")
    refresh_token: str = Field(..., description="JWT токен обновления")
    token_type: str = Field(default="bearer", description="Тип токена")
    user: UserResponse


class RefreshTokenRequest(SchemaBase):
    """Тело запроса для обновления токенов."""

    refresh_token: str = Field(..., description="JWT токен обновления")


class UserPrivacySettings(BaseModel):
    """
    Схема настроек приватности.
    Используется для генерации дефолтов и валидации в сервисах/схемах.
    """

    public_profile: bool = True
    show_contacts: bool = False
    show_github: bool = True
