"""
Репозиторий для работы с избранным (вакансии и компании).

Ключевые решения:
  - Используем selectinload для eager loading связанных данных
  - Проверяем существование opportunity/company перед добавлением
  - Используем INSERT ... ON CONFLICT DO NOTHING для идемпотентности
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from src.core.exceptions import NotFoundError, RepositoryError
from src.models.company import Company
from src.models.enums import OpportunityStatus
from src.models.opportunity import Opportunity
from src.models.social import Favorite, FavoriteCompany
from src.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class FavoriteRepository(BaseRepository[Favorite]):
    """Репозиторий для работы с избранными вакансиями."""

    model = Favorite

    async def get_user_favorites(
        self,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Favorite], int]:
        """
        Получить список избранных вакансий пользователя с пагинацией.
        """
        try:
            # Считаем total
            count_stmt = select(func.count()).select_from(Favorite).where(Favorite.user_id == user_id)
            total_result = await self.db.execute(count_stmt)
            total = total_result.scalar_one() or 0

            # Получаем избранное с eager loading
            stmt = (
                select(Favorite)
                .options(
                    selectinload(Favorite.opportunity).selectinload(Opportunity.company),
                    selectinload(Favorite.opportunity).selectinload(Opportunity.opportunity_tags),
                )
                .where(Favorite.user_id == user_id)
                .order_by(Favorite.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            result = await self.db.execute(stmt)
            favorites = list(result.scalars().unique().all())

            return favorites, total

        except SQLAlchemyError as e:
            logger.error("FavoriteRepository.get_user_favorites error: %s", e)
            raise RepositoryError() from e

    async def get_favorite_by_user_and_opportunity(
        self,
        user_id: UUID,
        opportunity_id: UUID,
    ) -> Favorite | None:
        """
        Проверить, есть ли вакансия в избранном у пользователя.
        """
        try:
            result = await self.db.execute(
                select(Favorite).where(
                    Favorite.user_id == user_id,
                    Favorite.opportunity_id == opportunity_id,
                )
            )
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error("FavoriteRepository.get_favorite_by_user_and_opportunity error: %s", e)
            raise RepositoryError() from e

    async def add_to_favorites(
        self,
        user_id: UUID,
        opportunity_id: UUID,
        note: str | None = None,
    ) -> Favorite:
        """
        Добавить вакансию в избранное.
        Проверяет существование вакансии и её статус.
        """
        try:
            # Проверяем существование вакансии
            opportunity = await self.db.get(Opportunity, opportunity_id)
            if not opportunity:
                raise NotFoundError(detail="Opportunity not found")

            if opportunity.status != OpportunityStatus.ACTIVE:
                raise RepositoryError(detail="Cannot favorite inactive opportunity")

            # Проверяем, не добавлено ли уже
            existing = await self.get_favorite_by_user_and_opportunity(user_id, opportunity_id)
            if existing:
                return existing

            # Создаём запись
            favorite = Favorite(user_id=user_id, opportunity_id=opportunity_id, note=note)
            self.db.add(favorite)
            await self.db.commit()
            await self.db.refresh(favorite)

            # Обновляем счётчик favorites_count у вакансии
            await self._increment_favorites_count(opportunity_id)

            return favorite

        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error("FavoriteRepository.add_to_favorites error: %s", e)
            raise RepositoryError() from e
        except NotFoundError:
            raise

    async def remove_from_favorites(
        self,
        user_id: UUID,
        opportunity_id: UUID,
    ) -> None:
        """
        Удалить вакансию из избранного.
        """
        try:
            # Находим запись
            favorite = await self.get_favorite_by_user_and_opportunity(user_id, opportunity_id)
            if not favorite:
                return  # Уже удалено или не было добавлено

            await self.db.delete(favorite)
            await self.db.commit()

            # Обновляем счётчик favorites_count у вакансии
            await self._decrement_favorites_count(opportunity_id)

        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error("FavoriteRepository.remove_from_favorites error: %s", e)
            raise RepositoryError() from e

    async def sync_favorites(
        self,
        user_id: UUID,
        opportunity_ids: list[UUID],
    ) -> list[UUID]:
        """
        Синхронизировать избранное с localStorage.
        Добавляет отсутствующие, оставляет существующие.
        Возвращает итоговый список ID.
        """
        try:
            if not opportunity_ids:
                return []

            # Получаем текущие избранные ID пользователя
            existing_stmt = select(Favorite.opportunity_id).where(Favorite.user_id == user_id)
            existing_result = await self.db.execute(existing_stmt)
            existing_ids = set(row[0] for row in existing_result.all())

            # Находим новые ID (которые есть в запросе, но нет в БД)
            new_ids = [oid for oid in opportunity_ids if oid not in existing_ids]

            # Проверяем существование и статус новых вакансий
            valid_opportunities = []
            if new_ids:
                opportunities_stmt = select(Opportunity.id).where(
                    Opportunity.id.in_(new_ids),
                    Opportunity.status == OpportunityStatus.ACTIVE,
                )
                opportunities_result = await self.db.execute(opportunities_stmt)
                valid_opportunities = [row[0] for row in opportunities_result.all()]

            # Добавляем новые записи массово
            if valid_opportunities:
                insert_stmt = insert(Favorite).values(
                    [{"user_id": user_id, "opportunity_id": oid, "note": None} for oid in valid_opportunities]
                )
                # ON CONFLICT DO NOTHING для идемпотентности
                insert_stmt = insert_stmt.on_conflict_do_nothing(index_elements=["user_id", "opportunity_id"])
                await self.db.execute(insert_stmt)

                # Обновляем счётчики у всех добавленных вакансий
                for oid in valid_opportunities:
                    await self._increment_favorites_count(oid)

            await self.db.commit()

            # Возвращаем итоговый список (существующие + новые валидные)
            return list(existing_ids | set(valid_opportunities))

        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error("FavoriteRepository.sync_favorites error: %s", e)
            raise RepositoryError() from e

    async def _increment_favorites_count(self, opportunity_id: UUID) -> None:
        """Атомарно увеличивает счётчик избранного у вакансии."""
        try:
            from sqlalchemy import update

            await self.db.execute(
                update(Opportunity)
                .where(Opportunity.id == opportunity_id)
                .values(favorites_count=Opportunity.favorites_count + 1)
            )
            await self.db.commit()
        except SQLAlchemyError as e:
            logger.warning("Failed to increment favorites count for %s: %s", opportunity_id, e)
            await self.db.rollback()

    async def _decrement_favorites_count(self, opportunity_id: UUID) -> None:
        """Атомарно уменьшает счётчик избранного у вакансии."""
        try:
            from sqlalchemy import update

            await self.db.execute(
                update(Opportunity)
                .where(Opportunity.id == opportunity_id)
                .values(favorites_count=func.greatest(Opportunity.favorites_count - 1, 0))
            )
            await self.db.commit()
        except SQLAlchemyError as e:
            logger.warning("Failed to decrement favorites count for %s: %s", opportunity_id, e)
            await self.db.rollback()


class FavoriteCompanyRepository(BaseRepository[FavoriteCompany]):
    """Репозиторий для работы с избранными компаниями."""

    model = FavoriteCompany

    async def get_user_favorite_companies(
        self,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[FavoriteCompany], int]:
        """
        Получить список избранных компаний пользователя с пагинацией.
        """
        try:
            # Считаем total
            count_stmt = select(func.count()).select_from(FavoriteCompany).where(FavoriteCompany.user_id == user_id)
            total_result = await self.db.execute(count_stmt)
            total = total_result.scalar_one() or 0

            # Получаем избранное с eager loading
            stmt = (
                select(FavoriteCompany)
                .options(selectinload(FavoriteCompany.company))
                .where(FavoriteCompany.user_id == user_id)
                .order_by(FavoriteCompany.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            result = await self.db.execute(stmt)
            favorites = list(result.scalars().unique().all())

            return favorites, total

        except SQLAlchemyError as e:
            logger.error("FavoriteCompanyRepository.get_user_favorite_companies error: %s", e)
            raise RepositoryError() from e

    async def get_favorite_company_by_user_and_company(
        self,
        user_id: UUID,
        company_id: UUID,
    ) -> FavoriteCompany | None:
        """
        Проверить, есть ли компания в избранном у пользователя.
        """
        try:
            result = await self.db.execute(
                select(FavoriteCompany).where(
                    FavoriteCompany.user_id == user_id,
                    FavoriteCompany.company_id == company_id,
                )
            )
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error("FavoriteCompanyRepository.get_favorite_company_by_user_and_company error: %s", e)
            raise RepositoryError() from e

    async def add_company_to_favorites(
        self,
        user_id: UUID,
        company_id: UUID,
    ) -> FavoriteCompany:
        """
        Добавить компанию в избранное.
        Проверяет существование компании.
        """
        try:
            # Проверяем существование компании
            company = await self.db.get(Company, company_id)
            if not company:
                raise NotFoundError(detail="Company not found")

            # Проверяем, не добавлена ли уже
            existing = await self.get_favorite_company_by_user_and_company(user_id, company_id)
            if existing:
                return existing

            # Создаём запись
            favorite = FavoriteCompany(user_id=user_id, company_id=company_id)
            self.db.add(favorite)
            await self.db.commit()
            await self.db.refresh(favorite)

            return favorite

        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error("FavoriteCompanyRepository.add_company_to_favorites error: %s", e)
            raise RepositoryError() from e
        except NotFoundError:
            raise

    async def remove_company_from_favorites(
        self,
        user_id: UUID,
        company_id: UUID,
    ) -> None:
        """
        Удалить компанию из избранного.
        """
        try:
            # Находим запись
            favorite = await self.get_favorite_company_by_user_and_company(user_id, company_id)
            if not favorite:
                return  # Уже удалено или не было добавлено

            await self.db.delete(favorite)
            await self.db.commit()

        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error("FavoriteCompanyRepository.remove_company_from_favorites error: %s", e)
            raise RepositoryError() from e

    async def sync_favorite_companies(
        self,
        user_id: UUID,
        company_ids: list[UUID],
    ) -> list[UUID]:
        """
        Синхронизировать избранное компаний с localStorage.
        Добавляет отсутствующие, оставляет существующие.
        Возвращает итоговый список ID.
        """
        try:
            if not company_ids:
                return []

            # Получаем текущие избранные ID компаний пользователя
            existing_stmt = select(FavoriteCompany.company_id).where(FavoriteCompany.user_id == user_id)
            existing_result = await self.db.execute(existing_stmt)
            existing_ids = set(row[0] for row in existing_result.all())

            # Находим новые ID (которые есть в запросе, но нет в БД)
            new_ids = [cid for cid in company_ids if cid not in existing_ids]

            # Проверяем существование компаний
            valid_companies = []
            if new_ids:
                companies_stmt = select(Company.id).where(
                    Company.id.in_(new_ids),
                    Company.is_active == True,  # noqa: E712
                )
                companies_result = await self.db.execute(companies_stmt)
                valid_companies = [row[0] for row in companies_result.all()]

            # Добавляем новые записи массово
            if valid_companies:
                insert_stmt = insert(FavoriteCompany).values([{"user_id": user_id, "company_id": cid} for cid in valid_companies])
                # ON CONFLICT DO NOTHING для идемпотентности
                insert_stmt = insert_stmt.on_conflict_do_nothing(index_elements=["user_id", "company_id"])
                await self.db.execute(insert_stmt)

            await self.db.commit()

            # Возвращаем итоговый список (существующие + новые валидные)
            return list(existing_ids | set(valid_companies))

        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error("FavoriteCompanyRepository.sync_favorite_companies error: %s", e)
            raise RepositoryError() from e
