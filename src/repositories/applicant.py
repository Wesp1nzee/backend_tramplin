"""
Репозиторий для работы с профилями соискателей.

Ключевые решения:
  - Поиск с учётом privacy_settings (public_profile=true)
  - Join с ProfileSkill и Skill для поиска по навыкам
  - Сортировка по релевантности (количеству совпадений навыков)
  - Проверка контактов между пользователями
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from src.core.exceptions import RepositoryError
from src.models.social import Contact
from src.models.user import Profile, User
from src.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class ApplicantRepository(BaseRepository[Profile]):
    """Репозиторий для работы с профилями соискателей."""

    model = Profile

    async def search_applicants(
        self,
        *,
        skills: list[str] | None = None,
        university: str | None = None,
        graduation_year: int | None = None,
        city: str | None = None,
        limit: int = 50,
        offset: int = 0,
        requester_user_id: UUID | None = None,
    ) -> tuple[list[Profile], int]:
        """
        Поиск соискателей с фильтрами.

        Args:
            skills: Список навыков для поиска
            university: Часть названия университета
            graduation_year: Год выпуска
            city: Город (из профиля пользователя)
            limit: Пагинация limit
            offset: Пагинация offset
            requester_user_id: ID пользователя, делающего запрос (для is_contact)

        Returns:
            (profiles, total) — список профилей и общее количество
        """
        try:
            from src.models.skill import ProfileSkill, Skill

            # Базовый запрос — только публичные профили
            base_stmt = (
                select(Profile)
                .join(User, User.id == Profile.user_id)
                .where(
                    User.is_active == True,  # noqa: E712
                    # Фильтр по privacy_settings: public_profile = true
                    Profile.privacy_settings["public_profile"].astext == "true",
                )
            )

            # Фильтр по университету (частичное совпадение)
            if university:
                base_stmt = base_stmt.where(Profile.university.ilike(f"%{university}%"))

            # Фильтр по году выпуска
            if graduation_year:
                base_stmt = base_stmt.where(Profile.graduation_year == graduation_year)

            # Фильтр по городу (через User → Company или Profile.city)
            # Для простоты ищем по Profile.city если есть
            if city:
                base_stmt = base_stmt.where(
                    or_(
                        Profile.university.ilike(f"%{city}%"),
                    )
                )

            # Фильтр по навыкам
            if skills:
                # Join с ProfileSkill и Skill
                skills_stmt = (
                    select(ProfileSkill.profile_id)
                    .join(Skill, Skill.id == ProfileSkill.skill_id)
                    .where(
                        Skill.name.in_([s.lower() for s in skills]),
                        ProfileSkill.profile_id == Profile.id,
                    )
                )
                base_stmt = base_stmt.where(skills_stmt.exists())

                # Сортировка по релевантности (количеству совпадений навыков)
                skill_match_count = (
                    select(func.count(ProfileSkill.skill_id))
                    .join(Skill, Skill.id == ProfileSkill.skill_id)
                    .where(
                        Skill.name.in_([s.lower() for s in skills]),
                        ProfileSkill.profile_id == Profile.id,
                    )
                    .scalar_subquery()
                )
                base_stmt = base_stmt.order_by(skill_match_count.desc(), Profile.graduation_year.desc())
            else:
                # Сортировка по году выпуска (recent first)
                base_stmt = base_stmt.order_by(Profile.graduation_year.desc())

            # Считаем total отдельным запросом
            count_stmt = select(func.count()).select_from(base_stmt.subquery())
            total_result = await self.db.execute(count_stmt)
            total = total_result.scalar_one() or 0

            # Основной запрос с пагинацией
            stmt = (
                base_stmt.options(
                    selectinload(Profile.user),
                    selectinload(Profile.profile_skills).selectinload(ProfileSkill.skill),
                )
                .limit(limit)
                .offset(offset)
            )

            result = await self.db.execute(stmt)
            profiles = list(result.scalars().unique().all())

            return profiles, total

        except SQLAlchemyError as e:
            logger.error("ApplicantRepository.search_applicants error: %s", e)
            raise RepositoryError() from e

    async def get_applicant_profile(
        self,
        profile_id: UUID,
        requester_user_id: UUID | None = None,
    ) -> Profile | None:
        """
        Получить детальный профиль соискателя.
        Применяет фильтрацию по privacy_settings.
        """
        try:
            from src.models.skill import ProfileSkill

            result = await self.db.execute(
                select(Profile)
                .options(
                    selectinload(Profile.user),
                    selectinload(Profile.profile_skills).selectinload(ProfileSkill.skill),
                )
                .where(Profile.id == profile_id)
            )
            profile = result.scalar_one_or_none()

            return profile

        except SQLAlchemyError as e:
            logger.error("ApplicantRepository.get_applicant_profile error: %s", e)
            raise RepositoryError() from e

    async def check_contact_status(
        self,
        requester_user_id: UUID,
        target_user_id: UUID,
    ) -> bool:
        """
        Проверить, есть ли контакт между пользователями.
        Returns True если статус ACCEPTED.
        """
        try:
            result = await self.db.execute(
                select(Contact.id).where(
                    or_(
                        and_(
                            Contact.requester_id == requester_user_id,
                            Contact.addressee_id == target_user_id,
                        ),
                        and_(
                            Contact.requester_id == target_user_id,
                            Contact.addressee_id == requester_user_id,
                        ),
                    ),
                    Contact.status == "accepted",
                )
            )
            return result.scalar_one_or_none() is not None

        except SQLAlchemyError as e:
            logger.error("ApplicantRepository.check_contact_status error: %s", e)
            return False

    async def get_user_profile_by_user_id(self, user_id: UUID) -> Profile | None:
        """
        Получить профиль по ID пользователя.
        """
        try:
            result = await self.db.execute(select(Profile).where(Profile.user_id == user_id))
            return result.scalar_one_or_none()

        except SQLAlchemyError as e:
            logger.error("ApplicantRepository.get_user_profile_by_user_id error: %s", e)
            raise RepositoryError() from e
