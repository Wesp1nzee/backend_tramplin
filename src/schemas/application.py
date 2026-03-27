"""
Pydantic DTO-схемы для откликов (Applications).

Используются только в API-слое — модели SQLAlchemy не проникают сюда.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.models.enums import ApplicationStatus


class SchemaBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ─── Вложенные объекты ───────────────────────────────────────


class ApplicantProfileShort(BaseModel):
    """Краткие данные профиля соискателя для работодателя."""

    id: uuid.UUID
    first_name: str
    last_name: str
    middle_name: str | None = None
    headline: str | None = None
    avatar_url: str | None = None
    university: str | None = None
    graduation_year: int | None = None
    cv_url: str | None = None
    privacy_settings: dict[str, bool] = Field(default_factory=dict)

    @property
    def full_name(self) -> str:
        parts = [self.last_name, self.first_name]
        if self.middle_name:
            parts.append(self.middle_name)
        return " ".join(parts)


class OpportunityShort(BaseModel):
    """Краткие данные вакансии/возможности."""

    id: uuid.UUID
    type: str
    title: str
    work_format: str
    employment_type: str | None = None
    experience_level: str | None = None
    city: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None


class CompanyShort(BaseModel):
    """Краткие данные компании."""

    id: uuid.UUID
    name: str
    logo_url: str | None = None
    city: str | None = None
    verification_status: str


class StatusHistoryItem(BaseModel):
    """Запись истории изменения статуса."""

    status: str
    changed_at: datetime
    changed_by: str  # "applicant" | "employer" | "system"


# ─── Запросы (Request DTO) ───────────────────────────────────


class ApplicationCreate(BaseModel):
    """Запрос на создание отклика."""

    opportunity_id: uuid.UUID = Field(..., description="ID вакансии/возможности")
    cover_letter: str | None = Field(None, max_length=5000, description="Сопроводительное письмо")


class ApplicationStatusUpdate(BaseModel):
    """Запрос на обновление статуса отклика."""

    status: ApplicationStatus = Field(..., description="Новый статус")
    employer_comment: str | None = Field(None, max_length=2000, description="Комментарий для соискателя")


class ApplicationFeedbackUpdate(BaseModel):
    """Запрос на добавление обратной связи от работодателя."""

    employer_comment: str | None = Field(None, max_length=2000, description="Комментарий для соискателя")
    employer_note: str | None = Field(None, max_length=2000, description="Внутренняя заметка")


# ─── Ответы (Response DTO) ───────────────────────────────────


class ApplicationResponse(BaseModel):
    """Детальная информация об отклике."""

    id: uuid.UUID
    opportunity_id: uuid.UUID
    applicant_id: uuid.UUID

    status: ApplicationStatus
    cover_letter: str | None = None
    cv_url_snapshot: str | None = None

    employer_comment: str | None = None
    employer_note: str | None = None

    status_history: list[StatusHistoryItem] = Field(default_factory=list)

    viewed_at: datetime | None = None
    responded_at: datetime | None = None
    is_shortlisted: bool = False

    created_at: datetime
    updated_at: datetime

    # Вложенные данные
    opportunity: OpportunityShort | None = None
    applicant_profile: ApplicantProfileShort | None = None
    company: CompanyShort | None = None


class ApplicationListItem(BaseModel):
    """Карточка отклика в списке."""

    id: uuid.UUID
    opportunity_id: uuid.UUID
    status: ApplicationStatus
    cover_letter: str | None = None
    cv_url_snapshot: str | None = None
    employer_comment: str | None = None
    is_shortlisted: bool = False

    created_at: datetime
    viewed_at: datetime | None = None
    responded_at: datetime | None = None

    # Вложенные данные
    opportunity: OpportunityShort | None = None
    company: CompanyShort | None = None


class ApplicationListResponse(BaseModel):
    """Ответ на GET /applications/me или GET /opportunities/{id}/applications."""

    items: list[ApplicationListItem] | list[ApplicationResponse]
    total: int
    limit: int
    offset: int


class ApplicationEmployerListItem(BaseModel):
    """Карточка отклика в списке для работодателя."""

    id: uuid.UUID
    opportunity_id: uuid.UUID
    applicant_id: uuid.UUID
    status: ApplicationStatus
    cover_letter: str | None = None
    is_shortlisted: bool = False

    created_at: datetime
    viewed_at: datetime | None = None
    responded_at: datetime | None = None

    # Данные соискателя (с учетом приватности)
    applicant_profile: ApplicantProfileShort | None = None


class ApplicationEmployerListResponse(BaseModel):
    """Ответ на GET /opportunities/{id}/applications для работодателя."""

    items: list[ApplicationEmployerListItem]
    total: int
    limit: int
    offset: int


class ApplicationEmployerDetail(BaseModel):
    """Детальная информация об отклике для работодателя."""

    id: uuid.UUID
    opportunity_id: uuid.UUID
    applicant_id: uuid.UUID

    status: ApplicationStatus
    cover_letter: str | None = None
    cv_url_snapshot: str | None = None

    employer_comment: str | None = None
    employer_note: str | None = None

    status_history: list[StatusHistoryItem] = Field(default_factory=list)

    viewed_at: datetime | None = None
    responded_at: datetime | None = None
    is_shortlisted: bool = False

    created_at: datetime
    updated_at: datetime

    # Данные соискателя (с учетом приватности)
    applicant_profile: ApplicantProfileShort | None = None
    opportunity: OpportunityShort | None = None


class ApplicationApplicantDetail(BaseModel):
    """Детальная информация об отклике для соискателя."""

    id: uuid.UUID
    opportunity_id: uuid.UUID
    status: ApplicationStatus
    cover_letter: str | None = None
    cv_url_snapshot: str | None = None

    employer_comment: str | None = None

    status_history: list[StatusHistoryItem] = Field(default_factory=list)

    viewed_at: datetime | None = None
    responded_at: datetime | None = None

    created_at: datetime
    updated_at: datetime

    # Данные вакансии
    opportunity: OpportunityShort | None = None
    company: CompanyShort | None = None
