"""
Бизнес-логика для глоссария платформы.

Сервис отвечает за:
  - Формирование списков навыков и тегов
  - Подготовку данных для справочников
  - Валидацию и трансформацию данных
"""

from __future__ import annotations

from src.repositories.glossary import GlossaryRepository
from src.schemas.glossary import (
    SkillListItem,
    SkillListResponse,
    TagListItem,
    TagListResponse,
)


class GlossaryService:
    def __init__(self, glossary_repo: GlossaryRepository) -> None:
        self.glossary_repo = glossary_repo

    async def get_skills(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        search: str | None = None,
        category: str | None = None,
    ) -> SkillListResponse:
        """
        Получить список навыков для справочника.

        Args:
            limit: Количество записей (default: 100)
            offset: Смещение для пагинации (default: 0)
            search: Поисковый запрос по названию
            category: Фильтр по категории (language, framework, etc.)

        Returns:
            SkillListResponse с элементами, категориями и пагинацией
        """
        skills, total = await self.glossary_repo.get_skills_list(
            limit=limit,
            offset=offset,
            search=search,
            category=category,
        )

        # Получаем список категорий для фильтров
        categories = await self.glossary_repo.get_skills_categories()

        items = [
            SkillListItem(
                id=skill.id,
                name=skill.name,
                slug=skill.slug,
                category=skill.category.value if skill.category else "other",
                icon_url=skill.icon_url,
                usage_count=skill.usage_count,
                is_system=skill.is_system,
            )
            for skill in skills
        ]

        return SkillListResponse(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
            categories=categories,
        )

    async def get_tags(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        search: str | None = None,
        category: str | None = None,
    ) -> TagListResponse:
        """
        Получить список тегов для справочника.

        Args:
            limit: Количество записей (default: 100)
            offset: Смещение для пагинации (default: 0)
            search: Поисковый запрос по названию
            category: Фильтр по категории (level, employment, etc.)

        Returns:
            TagListResponse с элементами, категориями и пагинацией
        """
        tags, total = await self.glossary_repo.get_tags_list(
            limit=limit,
            offset=offset,
            search=search,
            category=category,
        )

        # Получаем список категорий для фильтров
        categories = await self.glossary_repo.get_tags_categories()

        items = [
            TagListItem(
                id=tag.id,
                name=tag.name,
                slug=tag.slug,
                category=tag.category,
                color=tag.color,
                usage_count=tag.usage_count,
                is_system=tag.is_system,
            )
            for tag in tags
        ]

        return TagListResponse(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
            categories=categories,
        )
