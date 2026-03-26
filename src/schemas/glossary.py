"""
Схемы для глоссария платформы: навыки и теги.
Используются фронтендом для заполнения выпадающих списков,
автокомплитов и фильтров при создании/редактировании вакансий.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class SchemaBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ─── Навыки (Skills) ─────────────────────────────────────


class SkillListItem(SchemaBase):
    """
    Краткая информация о навыке для выбора в UI.
    """

    id: uuid.UUID
    name: str
    slug: str
    category: str  # SkillCategory as string: "language", "framework", etc.
    icon_url: str | None = None
    usage_count: int = Field(default=0, description="Популярность навыка")
    is_system: bool = Field(default=False, description="Системный навык (нельзя удалить)")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440001",
                "name": "Python",
                "slug": "python",
                "category": "language",
                "icon_url": "https://cdn.tramplin.ru/icons/python.svg",
                "usage_count": 1247,
                "is_system": True,
            }
        }


class SkillListResponse(BaseModel):
    """
    Ответ на GET /glossary/skills.
    Поддерживает пагинацию и поиск.
    """

    items: list[SkillListItem]
    total: int
    limit: int
    offset: int
    categories: list[str] = Field(
        default_factory=list,
        description="Доступные категории навыков для фильтрации",
    )


# ─── Теги (Tags) ─────────────────────────────────────────


class TagListItem(SchemaBase):
    """
    Краткая информация о теге для выбора в UI.
    """

    id: uuid.UUID
    name: str
    slug: str
    category: str | None = None  # "level", "employment", "direction", "special", etc.
    color: str | None = None  # HEX цвет для бейджа в UI
    usage_count: int = Field(default=0, description="Популярность тега")
    is_system: bool = Field(default=False, description="Системный тег")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440003",
                "name": "Senior",
                "slug": "senior",
                "category": "level",
                "color": "#EF4444",
                "usage_count": 892,
                "is_system": True,
            }
        }


class TagListResponse(BaseModel):
    """
    Ответ на GET /glossary/tags.
    """

    items: list[TagListItem]
    total: int
    limit: int
    offset: int
    categories: list[str] = Field(
        default_factory=list,
        description="Доступные категории тегов",
    )


# ─── Загрузка медиа ──────────────────────────────────────


class MediaUploadResponse(SchemaBase):
    """
    Ответ после успешной загрузки файла.
    """

    id: uuid.UUID
    url: str = Field(..., description="Публичный URL файла в хранилище")
    filename: str
    content_type: str
    size: int = Field(..., description="Размер файла в байтах")
    type: str = Field(..., description="Тип медиа: image, video, document")
    created_at: str  # ISO datetime

    class Config:
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440099",
                "url": "https://cdn.tramplin.ru/media/vacancies/python-dev.jpg",
                "filename": "python-dev.jpg",
                "content_type": "image/jpeg",
                "size": 245678,
                "type": "image",
                "created_at": "2024-01-15T10:30:00Z",
            }
        }


class MediaUploadError(BaseModel):
    """
    Структура ошибки при загрузке файла.
    """

    error: str
    detail: str | None = None
