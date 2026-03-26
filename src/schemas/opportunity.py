"""
Pydantic DTO-схемы для возможностей (вакансии, стажировки, мероприятия).

Используются только в API-слое — модели SQLAlchemy не проникают сюда.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SchemaBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ─── Вложенные объекты ───────────────────────────────────────


class CompanyShort(SchemaBase):
    """Краткие данные компании для карточки возможности."""

    id: uuid.UUID
    name: str
    logo_url: str | None = None
    city: str | None = None


class LocationInfo(SchemaBase):
    """Гео-данные для карточки."""

    lat: float | None = None
    lng: float | None = None
    address: str | None = None
    city: str | None = None


class SalaryInfo(SchemaBase):
    min: int | None = None
    max: int | None = None
    currency: str = "RUB"
    gross: bool = True


# ─── Список возможностей ─────────────────────────────────────


class OpportunityListItem(SchemaBase):
    """Карточка в списке — только нужные поля, без лишнего трафика."""

    id: uuid.UUID
    type: str
    title: str
    status: str
    work_format: str
    experience_level: str | None = None
    employment_type: str | None = None

    company: CompanyShort
    location: LocationInfo
    salary: SalaryInfo

    tags: list[str] = Field(default_factory=list)

    published_at: datetime | None = None
    expires_at: datetime | None = None
    # Для мероприятий
    event_start_at: datetime | None = None
    event_end_at: datetime | None = None
    max_participants: int | None = None
    current_participants: int = 0

    views_count: int = 0
    applications_count: int = 0


class OpportunityListResponse(BaseModel):
    """Ответ на GET /opportunities."""

    items: list[OpportunityListItem]
    total: int
    limit: int
    offset: int
    detected_city: str | None = Field(None, description="Город, определённый по IP или переданный явно")
    detected_from_ip: bool = Field(False, description="True если город определён по IP, а не передан явно")


# ─── Карта ───────────────────────────────────────────────────


class OpportunityMapMarker(BaseModel):
    """Маркер на карте — минимум данных для быстрой отдачи."""

    id: uuid.UUID
    type: str
    lat: float
    lng: float
    title: str
    company_name: str
    company_logo_url: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    work_format: str
    city: str | None = None


class OpportunityMapResponse(BaseModel):
    """Ответ на GET /opportunities/map."""

    markers: list[OpportunityMapMarker]
    total: int
    detected_city: str | None = None
    detected_from_ip: bool = False


# ─── Детальная карточка ──────────────────────────────────────


class OpportunityDetail(SchemaBase):
    """Полная карточка — GET /opportunities/{id}."""

    id: uuid.UUID
    type: str
    title: str
    status: str
    description: str | None = None
    requirements: str | None = None
    responsibilities: str | None = None

    work_format: str
    employment_type: str | None = None
    experience_level: str | None = None

    company: CompanyShort
    location: LocationInfo
    salary: SalaryInfo

    skills: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    contact_name: str | None = None
    contact_email: str | None = None
    contact_url: str | None = None

    published_at: datetime | None = None
    expires_at: datetime | None = None
    event_start_at: datetime | None = None
    event_end_at: datetime | None = None
    max_participants: int | None = None
    current_participants: int = 0

    views_count: int = 0
    applications_count: int = 0
    favorites_count: int = 0

    # Для авторизованного пользователя
    is_favorited: bool = False
    is_applied: bool = False


# ─── Фильтры ─────────────────────────────────────────────────


class FilterOption(BaseModel):
    value: str
    label: str
    count: int


class CityOption(BaseModel):
    name: str
    count: int


class SalaryRange(BaseModel):
    min: int | None = None
    max: int | None = None
    count: int


class OpportunityFiltersResponse(BaseModel):
    """Доступные фильтры для текущего набора данных."""

    cities: list[CityOption]
    types: list[FilterOption]
    work_formats: list[FilterOption]
    experience_levels: list[FilterOption]
    employment_types: list[FilterOption]
    salary_ranges: list[SalaryRange]
    detected_city: str | None = None


# ─── Query-параметры (для документации Swagger) ──────────────


class OpportunityQueryParams(BaseModel):
    """Параметры фильтрации для GET /opportunities."""

    city: str | None = None
    type: str | None = Field(None, description="Типы через запятую: vacancy,internship,event,mentoring")
    work_format: str | None = Field(None, description="office,hybrid,remote,online")
    experience_level: str | None = Field(None, description="intern,junior,middle,senior,lead")
    employment_type: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


# ════════════════════════════════════════════════════════════
#  CRUD DTO для работодателей (Employer)
# ════════════════════════════════════════════════════════════


class OpportunityCreate(BaseModel):
    """Запрос на создание вакансии/мероприятия."""

    type: str = Field(..., description="Тип: vacancy, internship, mentoring, event")
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, description="Описание возможности")
    requirements: str | None = Field(None, description="Требования к кандидату")
    responsibilities: str | None = Field(None, description="Обязанности")

    work_format: str = Field(..., description="office, hybrid, remote, online")
    employment_type: str | None = Field(None, description="full_time, part_time, project, volunteer")
    experience_level: str | None = Field(None, description="intern, junior, middle, senior, lead")

    # Зарплата
    salary_min: int | None = Field(None, ge=0)
    salary_max: int | None = Field(None, ge=0)
    salary_currency: str = Field(default="RUB", max_length=3)
    salary_gross: bool = Field(default=True)

    # Геолокация
    city: str | None = None
    address: str | None = None
    # Координаты для карты (lat, lng) — опционально
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)

    # Даты
    expires_at: datetime | None = None
    # Для мероприятий
    event_start_at: datetime | None = None
    event_end_at: datetime | None = None
    max_participants: int | None = Field(None, ge=1)

    # Контакты
    contact_name: str | None = None
    contact_email: EmailStr | None = None
    contact_phone: str | None = None
    contact_url: str | None = None

    # Навыки и теги (списки ID)
    skill_ids: list[uuid.UUID] = Field(default_factory=list)
    tag_ids: list[uuid.UUID] = Field(default_factory=list)

    # Медиа
    media: list[dict[str, str]] = Field(default_factory=list)


class OpportunityUpdate(BaseModel):
    """Запрос на обновление вакансии/мероприятия."""

    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    requirements: str | None = None
    responsibilities: str | None = None

    work_format: str | None = None
    employment_type: str | None = None
    experience_level: str | None = None

    # Зарплата
    salary_min: int | None = Field(None, ge=0)
    salary_max: int | None = Field(None, ge=0)
    salary_currency: str | None = Field(None, max_length=3)
    salary_gross: bool | None = None

    # Геолокация
    city: str | None = None
    address: str | None = None
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)

    # Даты
    expires_at: datetime | None = None
    # Для мероприятий
    event_start_at: datetime | None = None
    event_end_at: datetime | None = None
    max_participants: int | None = Field(None, ge=1)

    # Контакты
    contact_name: str | None = None
    contact_email: EmailStr | None = None
    contact_phone: str | None = None
    contact_url: str | None = None

    # Навыки и теги (списки ID)
    skill_ids: list[uuid.UUID] | None = None
    tag_ids: list[uuid.UUID] | None = None

    # Медиа
    media: list[dict[str, str]] | None = None


class OpportunityOwnerStats(BaseModel):
    """Расширенная статистика для владельца вакансии."""

    views_count: int = 0
    applications_count: int = 0
    favorites_count: int = 0
    # Статистика по откликам (если есть)
    pending_applications: int = 0
    accepted_applications: int = 0
    rejected_applications: int = 0


class OpportunityEmployerItem(SchemaBase):
    """Карточка в списке вакансий работодателя."""

    id: uuid.UUID
    type: str
    title: str
    status: str
    work_format: str
    employment_type: str | None = None
    experience_level: str | None = None

    location: LocationInfo
    salary: SalaryInfo

    tags: list[str] = Field(default_factory=list)

    created_at: datetime
    published_at: datetime | None = None
    expires_at: datetime | None = None

    # Для мероприятий
    event_start_at: datetime | None = None
    event_end_at: datetime | None = None

    stats: OpportunityOwnerStats


class OpportunityEmployerListResponse(BaseModel):
    """Ответ на GET /opportunities/me."""

    items: list[OpportunityEmployerItem]
    total: int


class OpportunityEmployerDetail(SchemaBase):
    """Детальная информация для редактирования (Employer)."""

    id: uuid.UUID
    type: str
    title: str
    status: str
    description: str | None = None
    requirements: str | None = None
    responsibilities: str | None = None

    work_format: str
    employment_type: str | None = None
    experience_level: str | None = None

    # Зарплата
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    salary_gross: bool | None = None

    # Геолокация
    city: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    # Даты
    expires_at: datetime | None = None
    # Для мероприятий
    event_start_at: datetime | None = None
    event_end_at: datetime | None = None
    max_participants: int | None = None

    # Контакты
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    contact_url: str | None = None

    # Навыки и теги (ID)
    skill_ids: list[uuid.UUID] = Field(default_factory=list)
    tag_ids: list[uuid.UUID] = Field(default_factory=list)

    # Медиа
    media: list[dict[str, str]] = Field(default_factory=list)

    # Статистика
    stats: OpportunityOwnerStats

    created_at: datetime
    updated_at: datetime
    published_at: datetime | None = None
    moderation_comment: str | None = None


class OpportunityPublishRequest(BaseModel):
    """Запрос на публикацию черновика."""

    # Опционально: комментарий для куратора (если требуется модерация)
    curator_comment: str | None = Field(None, max_length=500)


class OpportunityPublishResponse(SchemaBase):
    """Ответ на POST /opportunities/{id}/publish."""

    id: uuid.UUID
    status: str
    message: str = "Opportunity published successfully"
    requires_moderation: bool = False
