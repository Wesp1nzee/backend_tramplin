"""
Эндпоинты глоссария — публичный доступ к справочникам платформы.

Публичные эндпоинты (гостевой режим):
  - GET /api/v1/glossary/skills      → список навыков
  - GET /api/v1/glossary/tags        → список тегов
  - GET /api/v1/glossary/categories  → категории для фильтров

Используются фронтендом для:
  - Заполнения выпадающих списков
  - Автокомплита при вводе
  - Фильтров при поиске вакансий
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.deps import get_db
from src.repositories.glossary import GlossaryRepository
from src.schemas.glossary import (
    SkillListResponse,
    TagListResponse,
)
from src.services.glossary import GlossaryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/glossary", tags=["Glossary"])


# ─── Dependency injection ─────────────────────────────────────


async def get_glossary_repository(db: AsyncSession = Depends(get_db)) -> GlossaryRepository:
    return GlossaryRepository(db)


async def get_glossary_service(
    glossary_repo: GlossaryRepository = Depends(get_glossary_repository),
) -> GlossaryService:
    return GlossaryService(glossary_repo)


# ─── Public endpoints ─────────────────────────────────────────


@router.get(
    "/skills",
    response_model=SkillListResponse,
    status_code=status.HTTP_200_OK,
    summary="Список навыков",
    description=(
        "Возвращает список навыков и технологий из глобального каталога платформы.\n\n"
        "**Параметры:**\n"
        "- `search` — поисковый запрос по названию навыка (поддержка частичного совпадения)\n"
        "- `category` — фильтр по категории: language, framework, database,\n"
        "  devops, cloud, mobile, ai_ml, design, management, soft, other\n"
        "- `limit` — количество записей (default: 100, max: 200)\n"
        "- `offset` — смещение для пагинации\n\n"
        "**Ответ содержит:**\n"
        "- `items` — список навыков с основной информацией\n"
        "- `total` — общее количество навыков\n"
        "- `categories` — доступные категории для фильтрации\n"
        "- `limit`, `offset` — параметры пагинации\n\n"
        "Навыки отсортированы по популярности (usage_count) и названию.\n\n"
        "📖 **Использование:** заполнение выпадающих списков, автокомплит при создании вакансий."
    ),
)
async def get_skills(
    search: str | None = Query(None, min_length=1, max_length=100, description="Поисковый запрос"),
    category: str | None = Query(None, description="Фильтр по категории"),
    limit: int = Query(default=100, ge=1, le=200, description="Количество записей"),
    offset: int = Query(default=0, ge=0, description="Смещение"),
    glossary_service: GlossaryService = Depends(get_glossary_service),
) -> SkillListResponse:
    """
    Получить список навыков для справочника.
    """
    return await glossary_service.get_skills(
        limit=limit,
        offset=offset,
        search=search,
        category=category,
    )


@router.get(
    "/tags",
    response_model=TagListResponse,
    status_code=status.HTTP_200_OK,
    summary="Список тегов",
    description=(
        "Возвращает список тегов из глобального каталога платформы.\n\n"
        "**Параметры:**\n"
        "- `search` — поисковый запрос по названию тега (поддержка частичного совпадения)\n"
        "- `category` — фильтр по категории: level, employment, direction, special, etc.\n"
        "- `limit` — количество записей (default: 100, max: 200)\n"
        "- `offset` — смещение для пагинации\n\n"
        "**Ответ содержит:**\n"
        "- `items` — список тегов с основной информацией (включая цвет для UI-бейджей)\n"
        "- `total` — общее количество тегов\n"
        "- `categories` — доступные категории для фильтрации\n"
        "- `limit`, `offset` — параметры пагинации\n\n"
        "Теги отсортированы по популярности (usage_count) и названию.\n\n"
        "📖 **Использование:** заполнение выпадающих списков, автокомплит, фильтрация вакансий."
    ),
)
async def get_tags(
    search: str | None = Query(None, min_length=1, max_length=100, description="Поисковый запрос"),
    category: str | None = Query(None, description="Фильтр по категории"),
    limit: int = Query(default=100, ge=1, le=200, description="Количество записей"),
    offset: int = Query(default=0, ge=0, description="Смещение"),
    glossary_service: GlossaryService = Depends(get_glossary_service),
) -> TagListResponse:
    """
    Получить список тегов для справочника.
    """
    return await glossary_service.get_tags(
        limit=limit,
        offset=offset,
        search=search,
        category=category,
    )


@router.get(
    "/categories",
    status_code=status.HTTP_200_OK,
    summary="Категории для фильтров",
    description=(
        "Возвращает все доступные категории для навыков и тегов.\n\n"
        "**Ответ содержит:**\n"
        "- `skill_categories` — категории навыков (language, framework, database,\n"
        "  devops, cloud, mobile, ai_ml, design, management, soft, other)\n"
        "- `tag_categories` — категории тегов (level, employment, direction, special, etc.)\n\n"
        "📖 **Использование:** построение фильтров в UI, валидация параметров."
    ),
)
async def get_categories(
    glossary_repo: GlossaryRepository = Depends(get_glossary_repository),
) -> dict[str, list[str]]:
    """
    Получить все категории для навыков и тегов.
    """
    skill_categories = await glossary_repo.get_skills_categories()
    tag_categories = await glossary_repo.get_tags_categories()

    return {
        "skill_categories": skill_categories,
        "tag_categories": tag_categories,
    }
