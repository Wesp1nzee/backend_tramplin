"""
Репозиторий откликов (Applications).

Ключевые решения:
  - Используем selectinload для загрузки связанных данных (opportunity, applicant_profile, company)
  - Проверка дублей через unique constraint на уровне БД + предварительная проверка
  - Пагинация через limit/offset с подсчётом total
  - История изменений статуса хранится в JSONB-колонке
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import Select

from src.core.exceptions import RepositoryError
from src.models.application import Application
from src.models.company import Company
from src.models.enums import ApplicationStatus, OpportunityStatus, VerificationStatus
from src.models.opportunity import Opportunity
from src.models.user import Profile
from src.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class ApplicationRepository(BaseRepository[Application]):
    model = Application

    def _base_application_query(self) -> Select[tuple[Application]]:
        """
        Базовый запрос с загрузкой основных связей.
        """
        return select(Application).options(
            selectinload(Application.opportunity).selectinload(Opportunity.company),
            selectinload(Application.applicant_profile).selectinload(Profile.user),
        )

    def _base_employer_query(self) -> Select[tuple[Application]]:
        """
        Базовый запрос для работодателя с загрузкой данных соискателя.
        """
        return select(Application).options(
            selectinload(Application.applicant_profile).selectinload(Profile.user),
            selectinload(Application.opportunity).selectinload(Opportunity.company),
        )

    async def get_by_id_with_relations(self, application_id: UUID) -> Application | None:
        """
        Получить отклик по ID с загрузкой всех связей.

        Returns:
            Application с загруженными opportunity, applicant_profile, company
        """
        try:
            result = await self.db.execute(self._base_application_query().where(Application.id == application_id))
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error("ApplicationRepository.get_by_id_with_relations error: %s", e)
            raise RepositoryError() from e

    async def get_by_id_for_employer(
        self,
        application_id: UUID,
        company_id: UUID,
    ) -> Application | None:
        """
        Получить отклик для работодателя (проверка принадлежности компании).
        """
        try:
            result = await self.db.execute(
                self._base_employer_query()
                .join(Opportunity, Opportunity.id == Application.opportunity_id)
                .where(
                    Application.id == application_id,
                    Opportunity.company_id == company_id,
                )
            )
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error("ApplicationRepository.get_by_id_for_employer error: %s", e)
            raise RepositoryError() from e

    async def get_applicant_applications(
        self,
        applicant_id: UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Application], int]:
        """
        Получить список откликов соискателя с пагинацией.
        """
        try:
            # Считаем total
            count_stmt = select(func.count()).select_from(Application).where(Application.applicant_id == applicant_id)
            total_result = await self.db.execute(count_stmt)
            total = total_result.scalar_one() or 0

            # Получаем отклики
            stmt = (
                self._base_application_query()
                .where(Application.applicant_id == applicant_id)
                .order_by(Application.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            result = await self.db.execute(stmt)
            applications = list(result.scalars().unique().all())

            return applications, total

        except SQLAlchemyError as e:
            logger.error("ApplicationRepository.get_applicant_applications error: %s", e)
            raise RepositoryError() from e

    async def get_opportunity_applications(
        self,
        opportunity_id: UUID,
        company_id: UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Application], int]:
        """
        Получить список откликов на вакансию для работодателя.
        Проверяет принадлежность вакансии компании.
        """
        try:
            # Считаем total
            count_stmt = (
                select(func.count())
                .select_from(Application)
                .join(Opportunity, Opportunity.id == Application.opportunity_id)
                .where(
                    Application.opportunity_id == opportunity_id,
                    Opportunity.company_id == company_id,
                )
            )
            total_result = await self.db.execute(count_stmt)
            total = total_result.scalar_one() or 0

            # Получаем отклики
            stmt = (
                self._base_employer_query()
                .join(Opportunity, Opportunity.id == Application.opportunity_id)
                .where(
                    Application.opportunity_id == opportunity_id,
                    Opportunity.company_id == company_id,
                )
                .order_by(Application.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            result = await self.db.execute(stmt)
            applications = list(result.scalars().unique().all())

            return applications, total

        except SQLAlchemyError as e:
            logger.error("ApplicationRepository.get_opportunity_applications error: %s", e)
            raise RepositoryError() from e

    async def check_duplicate(
        self,
        opportunity_id: UUID,
        applicant_id: UUID,
    ) -> bool:
        """
        Проверить наличие существующего отклика.

        Returns:
            True если отклик уже существует
        """
        try:
            result = await self.db.execute(
                select(Application.id).where(
                    Application.opportunity_id == opportunity_id,
                    Application.applicant_id == applicant_id,
                )
            )
            return result.scalar_one_or_none() is not None
        except SQLAlchemyError as e:
            logger.error("ApplicationRepository.check_duplicate error: %s", e)
            raise RepositoryError() from e

    async def create_with_cv_snapshot(
        self,
        opportunity_id: UUID,
        applicant_id: UUID,
        cv_url_snapshot: str | None,
        cover_letter: str | None = None,
    ) -> Application:
        """
        Создать отклик с снапшотом резюме.
        """
        try:
            application = Application(
                opportunity_id=opportunity_id,
                applicant_id=applicant_id,
                cv_url_snapshot=cv_url_snapshot,
                cover_letter=cover_letter,
                status=ApplicationStatus.PENDING,
                status_history=[],
            )
            self.db.add(application)
            await self.db.flush()
            await self.db.refresh(application)

            # Загружаем связи для возврата
            result = await self.db.execute(self._base_application_query().where(Application.id == application.id))
            return result.scalar_one()

        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error("ApplicationRepository.create_with_cv_snapshot error: %s", e)
            raise RepositoryError() from e

    async def update_status(
        self,
        application: Application,
        new_status: ApplicationStatus,
        changed_by: str,
        employer_comment: str | None = None,
    ) -> Application:
        """
        Обновить статус отклика с записью в историю.

        Args:
            application: Объект Application для обновления
            new_status: Новый статус
            changed_by: Кто изменил статус ("applicant", "employer", "system")
            employer_comment: Комментарий работодателя (опционально)

        Returns:
            Обновлённый объект Application
        """
        try:
            # Обновляем статус
            application.status = new_status

            # Добавляем запись в историю
            history_entry = {
                "status": new_status.value,
                "changed_at": datetime.now(UTC).isoformat(),
                "changed_by": changed_by,
            }

            # Получаем текущую историю (может быть None)
            current_history = application.status_history or []
            current_history.append(history_entry)
            application.status_history = current_history

            # Обновляем комментарий если передан
            if employer_comment is not None:
                application.employer_comment = employer_comment

            # Устанавливаем дату просмотра если статус VIEWED
            if new_status == ApplicationStatus.VIEWED and application.viewed_at is None:
                application.viewed_at = datetime.now(UTC)

            # Устанавливаем дату ответа если статус ACCEPTED/REJECTED/RESERVE
            if new_status in (ApplicationStatus.ACCEPTED, ApplicationStatus.REJECTED, ApplicationStatus.RESERVE):
                if application.responded_at is None:
                    application.responded_at = datetime.now(UTC)

            await self.db.commit()
            await self.db.refresh(application)

            # Перезагружаем связи
            result = await self.db.execute(self._base_application_query().where(Application.id == application.id))
            return result.scalar_one()

        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error("ApplicationRepository.update_status error: %s", e)
            raise RepositoryError() from e

    async def withdraw_application(self, application: Application) -> Application:
        """
        Отозвать отклик (смена статуса на WITHDRAWN).
        """
        try:
            application.status = ApplicationStatus.WITHDRAWN

            # Добавляем запись в историю
            history_entry = {
                "status": ApplicationStatus.WITHDRAWN.value,
                "changed_at": datetime.now(UTC).isoformat(),
                "changed_by": "applicant",
            }
            current_history = application.status_history or []
            current_history.append(history_entry)
            application.status_history = current_history

            await self.db.commit()
            await self.db.refresh(application)

            # Перезагружаем связи
            result = await self.db.execute(self._base_application_query().where(Application.id == application.id))
            return result.scalar_one()

        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error("ApplicationRepository.withdraw_application error: %s", e)
            raise RepositoryError() from e

    async def update_feedback(
        self,
        application: Application,
        employer_comment: str | None = None,
        employer_note: str | None = None,
    ) -> Application:
        """
        Обновить обратную связь от работодателя.
        """
        try:
            if employer_comment is not None:
                application.employer_comment = employer_comment
            if employer_note is not None:
                application.employer_note = employer_note

            await self.db.commit()
            await self.db.refresh(application)

            # Перезагружаем связи
            result = await self.db.execute(self._base_application_query().where(Application.id == application.id))
            return result.scalar_one()

        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error("ApplicationRepository.update_feedback error: %s", e)
            raise RepositoryError() from e

    async def toggle_shortlist(
        self,
        application: Application,
        is_shortlisted: bool,
    ) -> Application:
        """
        Добавить/убрать отклик из избранного (shortlist).
        """
        try:
            application.is_shortlisted = is_shortlisted
            await self.db.commit()
            await self.db.refresh(application)

            result = await self.db.execute(self._base_application_query().where(Application.id == application.id))
            return result.scalar_one()

        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error("ApplicationRepository.toggle_shortlist error: %s", e)
            raise RepositoryError() from e

    async def increment_applications_count(self, opportunity_id: UUID) -> None:
        """
        Атомарно увеличить счётчик откликов у вакансии.
        """
        try:
            await self.db.execute(
                update(Opportunity)
                .where(Opportunity.id == opportunity_id)
                .values(applications_count=Opportunity.applications_count + 1)
            )
            await self.db.commit()
        except SQLAlchemyError as e:
            logger.warning("Failed to increment applications_count for %s: %s", opportunity_id, e)
            # Не пробрасываем ошибку дальше — это не должно ломать создание отклика

    async def validate_opportunity_for_application(
        self,
        opportunity_id: UUID,
    ) -> tuple[Opportunity, Company] | None:
        """
        Проверить возможность отклика на вакансию.

        Returns:
            (Opportunity, Company) если вакансия активна и компания верифицирована
            None если проверка не пройдена
        """
        try:
            result = await self.db.execute(
                select(Opportunity, Company)
                .join(Company, Company.id == Opportunity.company_id)
                .where(
                    Opportunity.id == opportunity_id,
                    Opportunity.status == OpportunityStatus.ACTIVE,
                    Company.verification_status == VerificationStatus.APPROVED,
                    Company.is_active == True,  # noqa: E712
                )
            )
            row = result.one_or_none()
            if row:
                return row[0], row[1]
            return None
        except SQLAlchemyError as e:
            logger.error("ApplicationRepository.validate_opportunity_for_application error: %s", e)
            raise RepositoryError() from e

    async def get_applicant_profile_with_cv(self, applicant_id: UUID) -> Profile | None:
        """
        Получить профиль соискателя с CV для снапшота.
        """
        try:
            result = await self.db.execute(select(Profile).options(selectinload(Profile.user)).where(Profile.id == applicant_id))
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error("ApplicationRepository.get_applicant_profile_with_cv error: %s", e)
            raise RepositoryError() from e

    async def get_company_id_by_user(self, user_id: UUID) -> UUID | None:
        """
        Получить ID компании пользователя.
        """
        try:
            result = await self.db.execute(
                select(Company.id).where(Company.owner_id == user_id, Company.is_active == True)  # noqa: E712
            )
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error("ApplicationRepository.get_company_id_by_user error: %s", e)
            raise RepositoryError() from e
