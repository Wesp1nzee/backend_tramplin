import re
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from src.models.enums import UserRole


class SchemaBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserCreate(SchemaBase):
    """Схема для регистрации нового пользователя."""

    email: EmailStr
    password: str = Field(..., min_length=12, max_length=128)
    role: UserRole = UserRole.APPLICANT
    first_name: str = Field(..., min_length=2, max_length=100)
    last_name: str = Field(..., min_length=2, max_length=100)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters long")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError("Password must contain at least one special character")
        return v


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


class PasswordChangeRequest(SchemaBase):
    """Запрос на смену пароля."""

    old_password: str = Field(..., min_length=8, max_length=128, description="Текущий пароль")
    new_password: str = Field(..., min_length=12, max_length=128, description="Новый пароль")

    @field_validator("new_password")
    @classmethod
    def validate_new_password_strength(cls, v: str) -> str:
        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters long")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError("Password must contain at least one special character")
        return v


class PasswordResetRequest(SchemaBase):
    """Запрос на сброс пароля (отправка email)."""

    email: EmailStr = Field(..., description="Email пользователя")


class PasswordResetConfirm(SchemaBase):
    """Подтверждение сброса пароля (с токеном)."""

    token: str = Field(..., description="Токен сброса из email")
    new_password: str = Field(..., min_length=12, max_length=128, description="Новый пароль")

    @field_validator("new_password")
    @classmethod
    def validate_new_password_strength(cls, v: str) -> str:
        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters long")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError("Password must contain at least one special character")
        return v


class CuratorCreate(SchemaBase):
    """Схема для создания куратора (только администратором)."""

    email: EmailStr
    password: str = Field(..., min_length=12, max_length=128)
    first_name: str = Field(..., min_length=2, max_length=100)
    last_name: str = Field(..., min_length=2, max_length=100)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters long")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError("Password must contain at least one special character")
        return v


class EmployerVerifyRequest(SchemaBase):
    """Запрос на верификацию работодателя."""

    is_verified: bool = Field(..., description="Статус верификации")
