"""
Репозиторий для глоссария: навыки (Skills) и теги (Tags).

Отвечает за:
  - Получение списков навыков и тегов с пагинацией
  - Поиск по названию
  - Фильтрацию по категориям
  - Подсчёт общего количества
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import RepositoryError
from src.db.base import Base
from src.models.opportunity import Tag
from src.models.skill import Skill
from src.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class GlossaryRepository(BaseRepository[Base]):
    """
    Репозиторий для работы с глоссарием платформы.

    Объединяет методы для Skills и Tags, так как они используются
    совместно в публичных эндпоинтах для справочников.
    """

    model: type[Base] = Base  # Не используется напрямую

    async def get_skills_list(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        search: str | None = None,
        category: str | None = None,
    ) -> tuple[list[Skill], int]:
        """
        Получить список навыков с пагинацией, поиском и фильтрацией по категории.

        Returns:
            (skills, total_count)
        """
        try:
            # Базовый запрос — показываем системные и одобренные навыки
            query = select(Skill).where(
                (Skill.is_system == True) | (Skill.is_approved == True)  # noqa: E712
            )

            # Поиск по названию или slug
            if search:
                search_pattern = f"%{search}%"
                query = query.where((Skill.name.ilike(search_pattern)) | (Skill.slug.ilike(search_pattern)))

            # Фильтр по категории
            if category:
                query = query.where(Skill.category == category)

            # Считаем общее количество
            count_query = select(func.count()).select_from(query.subquery())
            total_result = await self.db.execute(count_query)
            total = total_result.scalar() or 0

            # Получаем данные с пагинацией
            query = query.order_by(Skill.usage_count.desc(), Skill.name).limit(limit).offset(offset)
            result = await self.db.execute(query)
            skills = list(result.scalars().all())

            return skills, total

        except SQLAlchemyError as e:
            logger.error(f"Database error in get_skills_list: {e}")
            raise RepositoryError() from e

    async def get_skills_categories(self) -> list[str]:
        """
        Получить список всех доступных категорий навыков.

        Returns:
            Список уникальных категорий из существующих навыков
        """
        try:
            query = select(Skill.category).distinct().order_by(Skill.category)
            result = await self.db.execute(query)
            categories: list[str] = [cat.value if hasattr(cat, "value") else cat for cat in result.scalars().all() if cat]
            return categories

        except SQLAlchemyError as e:
            logger.error(f"Database error in get_skills_categories: {e}")
            raise RepositoryError() from e

    async def get_tags_list(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        search: str | None = None,
        category: str | None = None,
    ) -> tuple[list[Tag], int]:
        """
        Получить список тегов с пагинацией, поиском и фильтрацией по категории.

        Returns:
            (tags, total_count)
        """
        try:
            # Базовый запрос — показываем системные и одобренные теги
            query = select(Tag).where(
                (Tag.is_system == True) | (Tag.is_approved == True)  # noqa: E712
            )

            # Поиск по названию или slug
            if search:
                search_pattern = f"%{search}%"
                query = query.where((Tag.name.ilike(search_pattern)) | (Tag.slug.ilike(search_pattern)))

            # Фильтр по категории
            if category:
                query = query.where(Tag.category == category)

            # Считаем общее количество
            count_query = select(func.count()).select_from(query.subquery())
            total_result = await self.db.execute(count_query)
            total = total_result.scalar() or 0

            # Получаем данные с пагинацией
            query = query.order_by(Tag.usage_count.desc(), Tag.name).limit(limit).offset(offset)
            result = await self.db.execute(query)
            tags = list(result.scalars().all())

            return tags, total

        except SQLAlchemyError as e:
            logger.error(f"Database error in get_tags_list: {e}")
            raise RepositoryError() from e

    async def get_tags_categories(self) -> list[str]:
        """
        Получить список всех доступных категорий тегов.

        Returns:
            Список уникальных категорий из существующих тегов
        """
        try:
            query = select(Tag.category).distinct().order_by(Tag.category)
            result = await self.db.execute(query)
            categories = [cat for cat in result.scalars().all() if cat]
            return categories

        except SQLAlchemyError as e:
            logger.error(f"Database error in get_tags_categories: {e}")
            raise RepositoryError() from e

    async def get_skill_by_id(self, skill_id: UUID) -> Skill | None:
        """Получить навык по ID."""
        try:
            return await self.db.get(Skill, skill_id)
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_skill_by_id: {e}")
            raise RepositoryError() from e

    async def get_tag_by_id(self, tag_id: UUID) -> Tag | None:
        """Получить тег по ID."""
        try:
            return await self.db.get(Tag, tag_id)
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_tag_by_id: {e}")
            raise RepositoryError() from e
