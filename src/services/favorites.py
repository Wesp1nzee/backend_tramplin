"""
Бизнес-логика для работы с избранным (вакансии и компании).

Сервис отвечает за:
  - Синхронизацию localStorage с БД
  - CRUD операции с избранными вакансиями и компаниями
  - Проверку валидности возможностей и компаний
  - Проверку на попытку добавить свою собственную компанию/вакансию
"""

from __future__ import annotations

import logging
from uuid import UUID

from src.core.exceptions import NotFoundError, PermissionDeniedError
from src.models.company import Company
from src.models.opportunity import Opportunity
from src.models.user import User
from src.repositories.favorites import FavoriteCompanyRepository, FavoriteRepository
from src.repositories.opportunity import OpportunityRepository
from src.schemas.favorites import (
    FavoriteCompanyItem,
    FavoriteCompanyListResponse,
    FavoriteOpportunityItem,
    FavoriteOpportunityListResponse,
    FavoriteSyncRequest,
    FavoriteSyncResponse,
)
from src.schemas.opportunity import CompanyShort, LocationInfo, OpportunityListItem, SalaryInfo

logger = logging.getLogger(__name__)


class FavoriteService:
    """Сервис для работы с избранными вакансиями."""

    def __init__(
        self,
        favorite_repo: FavoriteRepository,
        opportunity_repo: OpportunityRepository,
        favorite_company_repo: FavoriteCompanyRepository,
    ) -> None:
        self.favorite_repo = favorite_repo
        self.opportunity_repo = opportunity_repo
        self.favorite_company_repo = favorite_company_repo

    async def sync_favorites(
        self,
        user: User,
        data: FavoriteSyncRequest,
    ) -> FavoriteSyncResponse:
        """
        Синхронизировать избранное из localStorage при логине/регистрации.
        """
        # Синхронизируем вакансии и компании параллельно
        synced_opportunities = await self.favorite_repo.sync_favorites(
            user_id=user.id,
            opportunity_ids=data.opportunity_ids,
        )
        synced_companies = await self.favorite_company_repo.sync_favorite_companies(
            user_id=user.id,
            company_ids=data.company_ids,
        )

        return FavoriteSyncResponse(
            synced_opportunities=synced_opportunities,
            synced_companies=synced_companies,
        )

    async def get_user_favorites(self, user_id: UUID) -> FavoriteOpportunityListResponse:
        """
        Получить список избранных вакансий пользователя.
        """
        favorites, total = await self.favorite_repo.get_user_favorites(user_id=user_id)

        items = [
            FavoriteOpportunityItem(
                id=fav.id,
                opportunity=self._to_opportunity_list_item(fav.opportunity),
                note=fav.note,
                created_at=fav.created_at,
            )
            for fav in favorites
        ]

        return FavoriteOpportunityListResponse(items=items, total=total)

    async def add_to_favorites(
        self,
        user: User,
        opportunity_id: UUID,
        note: str | None = None,
    ) -> FavoriteOpportunityItem:
        """
        Добавить вакансию в избранное.
        Проверяет, что пользователь не пытается добавить вакансию своей компании.
        """
        # Проверяем, не является ли пользователь владельцем компании
        company_id = await self.opportunity_repo.get_company_id_by_user(user.id)
        opportunity = await self.opportunity_repo.get_detail(opportunity_id)

        if not opportunity:
            raise NotFoundError(detail="Opportunity not found")

        if company_id and opportunity.company_id == company_id:
            raise PermissionDeniedError(detail="Cannot favorite your own company's opportunities")

        # Добавляем в избранное
        favorite = await self.favorite_repo.add_to_favorites(
            user_id=user.id,
            opportunity_id=opportunity_id,
            note=note,
        )

        return FavoriteOpportunityItem(
            id=favorite.id,
            opportunity=self._to_opportunity_list_item(favorite.opportunity),
            note=favorite.note,
            created_at=favorite.created_at,
        )

    async def remove_from_favorites(self, user_id: UUID, opportunity_id: UUID) -> None:
        """
        Удалить вакансию из избранного.
        """
        await self.favorite_repo.remove_from_favorites(
            user_id=user_id,
            opportunity_id=opportunity_id,
        )

    def _to_opportunity_list_item(self, opportunity: Opportunity) -> OpportunityListItem:
        """Конвертирует ORM-модель в DTO."""
        return OpportunityListItem(
            id=opportunity.id,
            type=opportunity.type,
            title=opportunity.title,
            status=opportunity.status,
            work_format=opportunity.work_format,
            experience_level=opportunity.experience_level,
            employment_type=opportunity.employment_type,
            company=CompanyShort(
                id=opportunity.company.id,
                name=opportunity.company.name,
                logo_url=opportunity.company.logo_url,
                city=opportunity.company.city,
            ),
            location=LocationInfo(
                address=opportunity.address,
                city=opportunity.city,
            ),
            salary=SalaryInfo(
                min=opportunity.salary_min,
                max=opportunity.salary_max,
                currency=opportunity.salary_currency,
                gross=opportunity.salary_gross,
            ),
            tags=[],
            published_at=opportunity.published_at,
            expires_at=opportunity.expires_at,
            event_start_at=opportunity.event_start_at,
            event_end_at=opportunity.event_end_at,
            max_participants=opportunity.max_participants,
            current_participants=opportunity.current_participants,
            views_count=opportunity.views_count,
            applications_count=opportunity.applications_count,
        )


class FavoriteCompanyService:
    """Сервис для работы с избранными компаниями."""

    def __init__(self, favorite_company_repo: FavoriteCompanyRepository) -> None:
        self.favorite_company_repo = favorite_company_repo

    async def get_user_favorite_companies(self, user_id: UUID) -> FavoriteCompanyListResponse:
        """
        Получить список избранных компаний пользователя.
        """
        favorites, total = await self.favorite_company_repo.get_user_favorite_companies(
            user_id=user_id,
        )

        items = [
            FavoriteCompanyItem(
                id=fav.id,
                company=self._to_company_short(fav.company),
                created_at=fav.created_at,
            )
            for fav in favorites
        ]

        return FavoriteCompanyListResponse(items=items, total=total)

    async def add_company_to_favorites(
        self,
        user: User,
        company_id: UUID,
    ) -> FavoriteCompanyItem:
        """
        Добавить компанию в избранное.
        Проверяет, что пользователь не пытается добавить свою собственную компанию.
        """
        # Проверяем, не является ли пользователь владельцем компании
        user_company_id = await self.favorite_company_repo.db.execute(
            select(Company.id).where(Company.owner_id == user.id, Company.is_active == True)  # noqa: E712
        )
        user_company = user_company_id.scalar_one_or_none()

        if user_company and user_company == company_id:
            raise PermissionDeniedError(detail="Cannot favorite your own company")

        # Добавляем в избранное
        favorite = await self.favorite_company_repo.add_company_to_favorites(
            user_id=user.id,
            company_id=company_id,
        )

        return FavoriteCompanyItem(
            id=favorite.id,
            company=self._to_company_short(favorite.company),
            created_at=favorite.created_at,
        )

    async def remove_company_from_favorites(self, user_id: UUID, company_id: UUID) -> None:
        """
        Удалить компанию из избранного.
        """
        await self.favorite_company_repo.remove_company_from_favorites(
            user_id=user_id,
            company_id=company_id,
        )

    def _to_company_short(self, company: Company) -> CompanyShort:
        """Конвертирует ORM-модель в DTO."""
        return CompanyShort(
            id=company.id,
            name=company.name,
            logo_url=company.logo_url,
            city=company.city,
        )


from sqlalchemy import select  # noqa: E402
