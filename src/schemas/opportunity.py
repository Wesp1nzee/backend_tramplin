"""
Pydantic DTO-схемы для возможностей (вакансии, стажировки, мероприятия).

Используются только в API-слое — модели SQLAlchemy не проникают сюда.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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
