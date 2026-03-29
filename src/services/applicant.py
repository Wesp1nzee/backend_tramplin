"""
Бизнес-логика для поиска соискателей.

Сервис отвечает за:
  - Поиск соискателей с фильтрами (навыки, университет, год выпуска)
  - Применение privacy settings к результатам
  - Проверку контактов между пользователями
  - Формирование ответа с учётом приватности
"""

from __future__ import annotations

import logging
from uuid import UUID

from src.core.exceptions import NotFoundError
from src.models.enums import UserRole
from src.models.user import User
from src.repositories.applicant import ApplicantRepository
from src.schemas.user import (
    ApplicantDetailResponse,
    ApplicantSearchItem,
    ApplicantSearchResponse,
)

logger = logging.getLogger(__name__)


class ApplicantService:
    """Сервис для работы с профилями соискателей."""

    def __init__(self, applicant_repo: ApplicantRepository) -> None:
        self.applicant_repo = applicant_repo

    async def search_applicants(
        self,
        *,
        skills: list[str] | None = None,
        university: str | None = None,
        graduation_year: int | None = None,
        city: str | None = None,
        limit: int = 50,
        offset: int = 0,
        requester_user: User | None = None,
    ) -> ApplicantSearchResponse:
        """
        Поиск соискателей с фильтрами.
        """
        # Ищем профили
        profiles, total = await self.applicant_repo.search_applicants(
            skills=skills,
            university=university,
            graduation_year=graduation_year,
            city=city,
            limit=limit,
            offset=offset,
            requester_user_id=requester_user.id if requester_user else None,
        )

        # Проверяем контакты если есть requester
        contact_map = {}
        if requester_user:
            for profile in profiles:
                is_contact = await self.applicant_repo.check_contact_status(
                    requester_user_id=requester_user.id,
                    target_user_id=profile.user_id,
                )
                contact_map[profile.id] = is_contact

        # Формируем ответ
        items = [self._to_search_item(profile, contact_map.get(profile.id, False)) for profile in profiles]

        return ApplicantSearchResponse(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_applicant_detail(
        self,
        profile_id: UUID,
        requester_user: User,
    ) -> ApplicantDetailResponse:
        """
        Получить детальный профиль соискателя.
        Применяет фильтрацию по privacy_settings.
        """
        profile = await self.applicant_repo.get_applicant_profile(
            profile_id=profile_id,
            requester_user_id=requester_user.id,
        )

        if not profile:
            raise NotFoundError(detail="Applicant profile not found")

        # Проверяем приватность
        privacy_settings = profile.privacy_settings or {}
        public_profile = privacy_settings.get("public_profile", True)

        if not public_profile and requester_user.role != UserRole.CURATOR:
            # Профиль скрыт, показываем только базовую информацию
            return self._to_private_profile(profile)

        # Проверяем контакт
        is_contact = await self.applicant_repo.check_contact_status(
            requester_user_id=requester_user.id,
            target_user_id=profile.user_id,
        )

        return self._to_detail_response(profile, is_contact)

    def _to_search_item(self, profile: Profile, is_contact: bool = False) -> ApplicantSearchItem:
        """Конвертирует ORM-модель в DTO для поиска."""
        privacy_settings = profile.privacy_settings or {}
        public_profile = privacy_settings.get("public_profile", True)

        # Если профиль не публичный, скрываем данные
        if not public_profile:
            return ApplicantSearchItem(
                id=profile.id,
                first_name="Скрыто",
                last_name="Скрыто",
                university=None,
                graduation_year=None,
                skills=[],
                avatar_url=None,
                headline=None,
                is_contact=is_contact,
            )

        # Извлекаем навыки
        skills = [ps.skill.name for ps in profile.profile_skills if ps.skill]

        return ApplicantSearchItem(
            id=profile.id,
            first_name=profile.first_name,
            last_name=profile.last_name,
            university=profile.university,
            graduation_year=profile.graduation_year,
            skills=skills,
            avatar_url=profile.avatar_url,
            headline=profile.headline,
            is_contact=is_contact,
        )

    def _to_detail_response(self, profile: Profile, is_contact: bool = False) -> ApplicantDetailResponse:
        """Конвертирует ORM-модель в детальный DTO."""
        privacy_settings = profile.privacy_settings or {}
        public_profile = privacy_settings.get("public_profile", True)
        show_contacts = privacy_settings.get("show_contacts", False)

        # Если контакты скрыты, не показываем их
        phone = profile.phone if show_contacts or is_contact else None
        social_links = profile.social_links if show_contacts or is_contact else {}

        # Извлекаем навыки
        skills = [ps.skill.name for ps in profile.profile_skills if ps.skill]

        return ApplicantDetailResponse(
            id=profile.id,
            first_name=profile.first_name,
            last_name=profile.last_name,
            middle_name=profile.middle_name,
            university=profile.university,
            faculty=profile.faculty,
            specialization=profile.specialization,
            graduation_year=profile.graduation_year,
            study_year=profile.study_year,
            headline=profile.headline,
            bio=profile.bio,
            avatar_url=profile.avatar_url,
            phone=phone,
            social_links=social_links,
            portfolio_url=profile.portfolio_url,
            cv_url=profile.cv_url if show_contacts or is_contact else None,
            skills=skills,
            privacy_settings=privacy_settings,
            career_preferences=profile.career_preferences or {},
            show_full_data=public_profile,
            is_contact=is_contact,
        )

    def _to_private_profile(self, profile: Profile) -> ApplicantDetailResponse:
        """Возвращает минимальную информацию для скрытого профиля."""
        return ApplicantDetailResponse(
            id=profile.id,
            first_name="Скрыто",
            last_name="Скрыто",
            middle_name=None,
            university=None,
            faculty=None,
            specialization=None,
            graduation_year=None,
            study_year=None,
            headline=None,
            bio=None,
            avatar_url=None,
            phone=None,
            social_links={},
            portfolio_url=None,
            cv_url=None,
            skills=[],
            privacy_settings=profile.privacy_settings or {},
            career_preferences={},
            show_full_data=False,
            is_contact=False,
        )


# Импортируем в конце для избежания циклических зависимостей
from src.models.user import Profile  # noqa: E402
