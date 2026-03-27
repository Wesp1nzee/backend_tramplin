"""
Бизнес-логика откликов (Applications).

Сервис отвечает за:
  - Валидацию возможности отклика (статус вакансии, верификация компании)
  - Создание отклика с снапшотом резюме
  - Управление статусами откликов (status machine)
  - Проверку прав доступа (соискатель/работодатель)
  - Генерацию уведомлений
  - Историю изменений статуса
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from src.core.exceptions import (
    ApplicationAlreadyExistsError,
    ApplicationNotFoundError,
    ApplicationWithdrawNotAllowedError,
    CompanyNotVerifiedError,
    InvalidStatusTransitionError,
    NotFoundError,
    OpportunityNotActiveError,
    PermissionDeniedError,
)
from src.models.application import Application
from src.models.company import Company
from src.models.enums import ApplicationStatus, NotificationType, OpportunityStatus, VerificationStatus
from src.models.notification import Notification
from src.models.opportunity import Opportunity
from src.models.user import Profile
from src.repositories.application import ApplicationRepository
from src.schemas.application import (
    ApplicantProfileShort,
    ApplicationApplicantDetail,
    ApplicationCreate,
    ApplicationEmployerDetail,
    ApplicationEmployerListItem,
    ApplicationEmployerListResponse,
    ApplicationFeedbackUpdate,
    ApplicationListItem,
    ApplicationListResponse,
    ApplicationResponse,
    ApplicationStatusUpdate,
    CompanyShort,
    OpportunityShort,
    StatusHistoryItem,
)

logger = logging.getLogger(__name__)


class ApplicationService:
    def __init__(self, application_repo: ApplicationRepository) -> None:
        self.application_repo = application_repo

    # ════════════════════════════════════════════════════════════
    #  Методы для соискателя (Applicant)
    # ════════════════════════════════════════════════════════════

    async def create_application(
        self,
        applicant_id: UUID,
        data: ApplicationCreate,
    ) -> ApplicationResponse:
        """
        Создать отклик на вакансию.

        Проверки:
          - Вакансия активна (status=ACTIVE)
          - Компания верифицирована (verification_status=APPROVED)
          - Нет дублирующегося отклика
          - Профиль соискателя существует

        Делает:
          - Снапшот cv_url из профиля
          - Создаёт отклик
          - Инкрементирует applications_count у вакансии
          - Создаёт уведомление работодателю
        """
        # Проверяем наличие дубля
        if await self.application_repo.check_duplicate(data.opportunity_id, applicant_id):
            raise ApplicationAlreadyExistsError()

        # Валидируем вакансию и компанию
        validation_result = await self.application_repo.validate_opportunity_for_application(data.opportunity_id)
        if not validation_result:
            opportunity = await self.application_repo.db.get(Opportunity, data.opportunity_id)
            if not opportunity:
                raise NotFoundError(detail="Opportunity not found")

            # Проверяем статус вакансии
            if opportunity.status != OpportunityStatus.ACTIVE:
                raise OpportunityNotActiveError()

            # Проверяем компанию
            company = await self.application_repo.db.get(Company, opportunity.company_id)
            if not company or company.verification_status != VerificationStatus.APPROVED:
                raise CompanyNotVerifiedError()

            raise NotFoundError(detail="Opportunity validation failed")

        opportunity, company = validation_result

        # Получаем профиль соискателя для снапшота CV
        profile = await self.application_repo.get_applicant_profile_with_cv(applicant_id)
        if not profile:
            raise NotFoundError(detail="Applicant profile not found")

        # Создаём отклик с снапшотом резюме
        application = await self.application_repo.create_with_cv_snapshot(
            opportunity_id=data.opportunity_id,
            applicant_id=applicant_id,
            cv_url_snapshot=profile.cv_url,
            cover_letter=data.cover_letter,
        )

        # Инкрементируем счётчик откликов (не блокируя ответ)
        import asyncio

        asyncio.create_task(self.application_repo.increment_applications_count(data.opportunity_id))

        # Создаём уведомление работодателю
        await self._create_employer_notification(
            employer_id=company.owner_id,
            opportunity_id=opportunity.id,
            opportunity_title=opportunity.title,
            application_id=application.id,
        )

        return self._to_response_dto(application)

    async def get_applicant_applications(
        self,
        applicant_id: UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> ApplicationListResponse:
        """
        Получить список откликов соискателя с пагинацией.
        """
        applications, total = await self.application_repo.get_applicant_applications(
            applicant_id=applicant_id,
            limit=limit,
            offset=offset,
        )

        items = [self._to_list_item_dto(app) for app in applications]

        return ApplicationListResponse(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_applicant_application_detail(
        self,
        applicant_id: UUID,
        application_id: UUID,
    ) -> ApplicationApplicantDetail:
        """
        Получить детали отклика для соискателя.
        Проверяет что отклик принадлежит соискателю.
        """
        application = await self.application_repo.get_by_id_with_relations(application_id)
        if not application:
            raise ApplicationNotFoundError()

        # Проверка принадлежности
        if application.applicant_id != applicant_id:
            raise PermissionDeniedError(detail="You can only view your own applications")

        return self._to_applicant_detail_dto(application)

    async def withdraw_application(
        self,
        applicant_id: UUID,
        application_id: UUID,
    ) -> ApplicationApplicantDetail:
        """
        Отозвать отклик.

        Разрешено только если статус PENDING или VIEWED.
        Запрещено если ACCEPTED/REJECTED/RESERVE.
        """
        application = await self.application_repo.get_by_id_with_relations(application_id)
        if not application:
            raise ApplicationNotFoundError()

        # Проверка принадлежности
        if application.applicant_id != applicant_id:
            raise PermissionDeniedError(detail="You can only withdraw your own applications")

        # Проверка допустимости отзыва
        if application.status not in (ApplicationStatus.PENDING, ApplicationStatus.VIEWED):
            raise ApplicationWithdrawNotAllowedError(detail=f"Cannot withdraw application with status {application.status.value}")

        # Отозываем отклик
        application = await self.application_repo.withdraw_application(application)

        return self._to_applicant_detail_dto(application)

    # ════════════════════════════════════════════════════════════
    #  Методы для работодателя (Employer)
    # ════════════════════════════════════════════════════════════

    async def get_opportunity_applications(
        self,
        company_id: UUID,
        opportunity_id: UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> ApplicationEmployerListResponse:
        """
        Получить список откликов на вакансию работодателя.
        """
        applications, total = await self.application_repo.get_opportunity_applications(
            opportunity_id=opportunity_id,
            company_id=company_id,
            limit=limit,
            offset=offset,
        )

        items = [self._to_employer_list_item_dto(app) for app in applications]

        return ApplicationEmployerListResponse(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_employer_application_detail(
        self,
        company_id: UUID,
        application_id: UUID,
    ) -> ApplicationEmployerDetail:
        """
        Получить детали отклика для работодателя.
        Проверяет принадлежность вакансии компании.
        """
        application = await self.application_repo.get_by_id_for_employer(application_id, company_id)
        if not application:
            raise ApplicationNotFoundError()

        return self._to_employer_detail_dto(application)

    async def update_application_status(
        self,
        company_id: UUID,
        application_id: UUID,
        data: ApplicationStatusUpdate,
    ) -> ApplicationEmployerDetail:
        """
        Обновить статус отклика.

        Валидация переходов:
          PENDING → VIEWED → ACCEPTED / REJECTED / RESERVE
          PENDING → ACCEPTED / REJECTED / RESERVE (пропуская VIEWED)

        Запрещено:
          - Изменять статус отозванного отклика (WITHDRAWN)
          - Менять статус обратно на PENDING

        Отправляет уведомление соискателю.
        """
        application = await self.application_repo.get_by_id_for_employer(application_id, company_id)
        if not application:
            raise ApplicationNotFoundError()

        # Проверка допустимости перехода
        self._validate_status_transition(application.status, data.status)

        # Обновляем статус
        application = await self.application_repo.update_status(
            application=application,
            new_status=data.status,
            changed_by="employer",
            employer_comment=data.employer_comment,
        )

        # Создаём уведомление соискателю
        await self._create_applicant_status_notification(
            applicant_id=application.applicant_id,
            application_id=application.id,
            old_status=application.status,
            new_status=data.status,
            opportunity_title=application.opportunity.title if application.opportunity else "Вакансия",
        )

        return self._to_employer_detail_dto(application)

    async def update_application_feedback(
        self,
        company_id: UUID,
        application_id: UUID,
        data: ApplicationFeedbackUpdate,
    ) -> ApplicationEmployerDetail:
        """
        Обновить обратную связь от работодателя.
        """
        application = await self.application_repo.get_by_id_for_employer(application_id, company_id)
        if not application:
            raise ApplicationNotFoundError()

        application = await self.application_repo.update_feedback(
            application=application,
            employer_comment=data.employer_comment,
            employer_note=data.employer_note,
        )

        return self._to_employer_detail_dto(application)

    async def toggle_application_shortlist(
        self,
        company_id: UUID,
        application_id: UUID,
        is_shortlisted: bool,
    ) -> ApplicationEmployerDetail:
        """
        Добавить/убрать отклик из избранного (shortlist).
        """
        application = await self.application_repo.get_by_id_for_employer(application_id, company_id)
        if not application:
            raise ApplicationNotFoundError()

        application = await self.application_repo.toggle_shortlist(
            application=application,
            is_shortlisted=is_shortlisted,
        )

        return self._to_employer_detail_dto(application)

    # ════════════════════════════════════════════════════════════
    #  Вспомогательные методы
    # ════════════════════════════════════════════════════════════

    @staticmethod
    def _validate_status_transition(current_status: ApplicationStatus, new_status: ApplicationStatus) -> None:
        """
        Проверка допустимости перехода между статусами.

        Разрешённые переходы:
          PENDING → VIEWED, ACCEPTED, REJECTED, RESERVE
          VIEWED → ACCEPTED, REJECTED, RESERVE
          Любые → WITHDRAWN (только соискателем)
        """
        allowed_transitions: dict[ApplicationStatus, list[ApplicationStatus]] = {
            ApplicationStatus.PENDING: [
                ApplicationStatus.VIEWED,
                ApplicationStatus.ACCEPTED,
                ApplicationStatus.REJECTED,
                ApplicationStatus.RESERVE,
            ],
            ApplicationStatus.VIEWED: [
                ApplicationStatus.ACCEPTED,
                ApplicationStatus.REJECTED,
                ApplicationStatus.RESERVE,
            ],
        }

        # WITHDRAWN может установить только соискатель (через отдельный метод)
        if new_status == ApplicationStatus.WITHDRAWN:
            raise InvalidStatusTransitionError(detail="Status cannot be changed to WITHDRAWN by employer")

        if current_status not in allowed_transitions:
            raise InvalidStatusTransitionError(detail=f"Cannot change status from {current_status.value}")

        if new_status not in allowed_transitions[current_status]:
            raise InvalidStatusTransitionError(detail=f"Cannot transition from {current_status.value} to {new_status.value}")

    async def _create_employer_notification(
        self,
        employer_id: UUID,
        opportunity_id: UUID,
        opportunity_title: str,
        application_id: UUID,
    ) -> None:
        """
        Создать уведомление работодателю о новом отклике.
        """
        try:
            notification = Notification(
                recipient_id=employer_id,
                type=NotificationType.NEW_APPLICATION,
                title="Новый отклик на вакансию",
                body=f"Пользователь откликнулся на вакансию «{opportunity_title}»",
                payload={
                    "type": "application",
                    "id": str(application_id),
                    "opportunity_id": str(opportunity_id),
                    "url": f"/applications/{application_id}",
                },
            )
            self.application_repo.db.add(notification)
            await self.application_repo.db.commit()
        except Exception as e:
            logger.error("Failed to create employer notification: %s", e)
            # Не пробрасываем ошибку — уведомление не должно ломать создание отклика

    async def _create_applicant_status_notification(
        self,
        applicant_id: UUID,
        application_id: UUID,
        old_status: ApplicationStatus,
        new_status: ApplicationStatus,
        opportunity_title: str,
    ) -> None:
        """
        Создать уведомление соискателю об изменении статуса отклика.

        applicant_id — это ID профиля (profiles.id), поэтому нужно получить user_id
        из таблицы profiles для корректного создания уведомления (recipient_id -> users.id).
        """
        from sqlalchemy.exc import IntegrityError
        from sqlalchemy.ext.asyncio import AsyncSession

        db: AsyncSession = self.application_repo.db

        # Получаем профиль соискателя, чтобы найти user_id
        profile = await db.get(Profile, applicant_id)
        if not profile:
            logger.warning("Applicant profile %s not found for notification", applicant_id)
            return

        recipient_user_id = profile.user_id
        if not recipient_user_id:
            logger.warning("Profile %s has no user_id for notification", applicant_id)
            return

        # Используем SAVEPOINT, чтобы ошибка уведомления не ломала основную транзакцию
        async with db.begin_nested():
            try:
                status_titles = {
                    ApplicationStatus.VIEWED: "Ваш отклик просмотрен",
                    ApplicationStatus.ACCEPTED: "Ваш отклик одобрен",
                    ApplicationStatus.REJECTED: "Ваш отклик отклонён",
                    ApplicationStatus.RESERVE: "Ваш отклик в резерве",
                }

                status_bodies = {
                    ApplicationStatus.VIEWED: f"Работодатель просмотрел ваш отклик на вакансию «{opportunity_title}»",
                    ApplicationStatus.ACCEPTED: f"Поздравляем! Ваш отклик на вакансию «{opportunity_title}» одобрен",
                    ApplicationStatus.REJECTED: f"К сожалению, ваш отклик на вакансию «{opportunity_title}» отклонён",
                    ApplicationStatus.RESERVE: f"Ваш отклик на вакансию «{opportunity_title}» добавлен в резерв",
                }

                notification = Notification(
                    recipient_id=recipient_user_id,
                    type=NotificationType.APPLICATION_STATUS,
                    title=status_titles.get(new_status, "Статус отклика изменён"),
                    body=status_bodies.get(new_status, f"Статус вашего отклика изменён на {new_status.value}"),
                    payload={
                        "type": "application",
                        "id": str(application_id),
                        "opportunity_id": str(application_id),
                        "url": f"/applications/me/{application_id}",
                    },
                )
                db.add(notification)
                await db.flush()  # Флешим в рамках SAVEPOINT
            except IntegrityError as e:
                # Ошибка FK (recipient_id не найден в users) или другая ошибка целостности
                logger.error("Failed to create applicant status notification (IntegrityError): %s", e)
                raise  # Пробрасываем для rollback SAVEPOINT
            except Exception as e:
                logger.error("Failed to create applicant status notification: %s", e)
                raise  # Пробрасываем для rollback SAVEPOINT

    # ════════════════════════════════════════════════════════════
    #  Конвертеры ORM → DTO
    # ════════════════════════════════════════════════════════════

    def _to_response_dto(self, application: Application) -> ApplicationResponse:
        """Конвертирует ORM-модель в ApplicationResponse."""
        return ApplicationResponse(
            id=application.id,
            opportunity_id=application.opportunity_id,
            applicant_id=application.applicant_id,
            status=application.status,
            cover_letter=application.cover_letter,
            cv_url_snapshot=application.cv_url_snapshot,
            employer_comment=application.employer_comment,
            employer_note=application.employer_note,
            status_history=[
                StatusHistoryItem(
                    status=item["status"],
                    changed_at=datetime.fromisoformat(item["changed_at"]),
                    changed_by=item["changed_by"],
                )
                for item in (application.status_history or [])
            ],
            viewed_at=application.viewed_at,
            responded_at=application.responded_at,
            is_shortlisted=application.is_shortlisted,
            created_at=application.created_at,
            updated_at=application.updated_at,
            opportunity=self._to_opportunity_short(application.opportunity) if application.opportunity else None,
            applicant_profile=self._to_applicant_profile_short(application.applicant_profile)
            if application.applicant_profile
            else None,
            company=self._to_company_short(application.opportunity.company) if application.opportunity else None,
        )

    def _to_list_item_dto(self, application: Application) -> ApplicationListItem:
        """Конвертирует ORM-модель в ApplicationListItem."""
        return ApplicationListItem(
            id=application.id,
            opportunity_id=application.opportunity_id,
            status=application.status,
            cover_letter=application.cover_letter,
            cv_url_snapshot=application.cv_url_snapshot,
            employer_comment=application.employer_comment,
            is_shortlisted=application.is_shortlisted,
            created_at=application.created_at,
            viewed_at=application.viewed_at,
            responded_at=application.responded_at,
            opportunity=self._to_opportunity_short(application.opportunity) if application.opportunity else None,
            company=self._to_company_short(application.opportunity.company) if application.opportunity else None,
        )

    def _to_applicant_detail_dto(self, application: Application) -> ApplicationApplicantDetail:
        """Конвертирует ORM-модель в ApplicationApplicantDetail."""
        return ApplicationApplicantDetail(
            id=application.id,
            opportunity_id=application.opportunity_id,
            status=application.status,
            cover_letter=application.cover_letter,
            cv_url_snapshot=application.cv_url_snapshot,
            employer_comment=application.employer_comment,
            status_history=[
                StatusHistoryItem(
                    status=item["status"],
                    changed_at=datetime.fromisoformat(item["changed_at"]),
                    changed_by=item["changed_by"],
                )
                for item in (application.status_history or [])
            ],
            viewed_at=application.viewed_at,
            responded_at=application.responded_at,
            created_at=application.created_at,
            updated_at=application.updated_at,
            opportunity=self._to_opportunity_short(application.opportunity) if application.opportunity else None,
            company=self._to_company_short(application.opportunity.company) if application.opportunity else None,
        )

    def _to_employer_list_item_dto(self, application: Application) -> ApplicationEmployerListItem:
        """Конвертирует ORM-модель в ApplicationEmployerListItem."""
        return ApplicationEmployerListItem(
            id=application.id,
            opportunity_id=application.opportunity_id,
            applicant_id=application.applicant_id,
            status=application.status,
            cover_letter=application.cover_letter,
            is_shortlisted=application.is_shortlisted,
            created_at=application.created_at,
            viewed_at=application.viewed_at,
            responded_at=application.responded_at,
            applicant_profile=self._to_applicant_profile_short(application.applicant_profile)
            if application.applicant_profile
            else None,
        )

    def _to_employer_detail_dto(self, application: Application) -> ApplicationEmployerDetail:
        """Конвертирует ORM-модель в ApplicationEmployerDetail."""
        return ApplicationEmployerDetail(
            id=application.id,
            opportunity_id=application.opportunity_id,
            applicant_id=application.applicant_id,
            status=application.status,
            cover_letter=application.cover_letter,
            cv_url_snapshot=application.cv_url_snapshot,
            employer_comment=application.employer_comment,
            employer_note=application.employer_note,
            status_history=[
                StatusHistoryItem(
                    status=item["status"],
                    changed_at=datetime.fromisoformat(item["changed_at"]),
                    changed_by=item["changed_by"],
                )
                for item in (application.status_history or [])
            ],
            viewed_at=application.viewed_at,
            responded_at=application.responded_at,
            is_shortlisted=application.is_shortlisted,
            created_at=application.created_at,
            updated_at=application.updated_at,
            applicant_profile=self._to_applicant_profile_short(application.applicant_profile)
            if application.applicant_profile
            else None,
            opportunity=self._to_opportunity_short(application.opportunity) if application.opportunity else None,
        )

    @staticmethod
    def _to_opportunity_short(opportunity: Opportunity) -> OpportunityShort | None:
        """Конвертирует Opportunity в OpportunityShort."""
        if not opportunity:
            return None
        return OpportunityShort(
            id=opportunity.id,
            type=opportunity.type,
            title=opportunity.title,
            work_format=opportunity.work_format,
            employment_type=opportunity.employment_type,
            experience_level=opportunity.experience_level,
            city=opportunity.city,
            salary_min=opportunity.salary_min,
            salary_max=opportunity.salary_max,
            salary_currency=opportunity.salary_currency,
        )

    @staticmethod
    def _to_applicant_profile_short(profile: Profile) -> ApplicantProfileShort | None:
        """Конвертирует Profile в ApplicantProfileShort с учётом приватности."""
        if not profile:
            return None

        privacy = profile.privacy_settings or {}
        show_full = privacy.get("public_profile", True)

        return ApplicantProfileShort(
            id=profile.id,
            first_name=profile.first_name if show_full else "Скрыто",
            last_name=profile.last_name if show_full else "Скрыто",
            middle_name=profile.middle_name if show_full else None,
            headline=profile.headline if show_full else None,
            avatar_url=profile.avatar_url if show_full else None,
            university=profile.university if show_full else None,
            graduation_year=profile.graduation_year if show_full else None,
            cv_url=profile.cv_url if show_full else None,
            privacy_settings=privacy,
        )

    @staticmethod
    def _to_company_short(company: Company) -> CompanyShort | None:
        """Конвертирует Company в CompanyShort."""
        if not company:
            return None
        return CompanyShort(
            id=company.id,
            name=company.name,
            logo_url=company.logo_url,
            city=company.city,
            verification_status=company.verification_status.value if company.verification_status else "pending",
        )
