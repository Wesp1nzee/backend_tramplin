"""
Pydantic DTO-схемы для избранного (вакансии и компании).

Используются только в API-слое — модели SQLAlchemy не проникают сюда.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.opportunity import CompanyShort, OpportunityListItem


class SchemaBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ─── Запросы на синхронизацию ─────────────────────────────────


class FavoriteSyncRequest(BaseModel):
    """Запрос на синхронизацию избранного из localStorage."""

    opportunity_ids: list[uuid.UUID] = Field(default_factory=list, description="ID вакансий из localStorage")
    company_ids: list[uuid.UUID] = Field(default_factory=list, description="ID компаний из localStorage")


class FavoriteSyncResponse(BaseModel):
    """Ответ на синхронизацию избранного."""

    synced_opportunities: list[uuid.UUID] = Field(default_factory=list, description="ID синхронизированных вакансий")
    synced_companies: list[uuid.UUID] = Field(default_factory=list, description="ID синхронизированных компаний")


# ─── Избранные вакансии ──────────────────────────────────────


class FavoriteOpportunityCreate(BaseModel):
    """Запрос на добавление вакансии в избранное."""

    note: str | None = Field(None, max_length=1000, description="Пользовательская заметка")


class FavoriteOpportunityUpdate(BaseModel):
    """Запрос на обновление заметки к избранной вакансии."""

    note: str | None = Field(None, max_length=1000, description="Пользовательская заметка")


class FavoriteOpportunityItem(SchemaBase):
    """Элемент списка избранных вакансий."""

    id: uuid.UUID
    opportunity: OpportunityListItem
    note: str | None = None
    created_at: datetime


class FavoriteOpportunityListResponse(BaseModel):
    """Ответ на GET /favorites/opportunities."""

    items: list[FavoriteOpportunityItem]
    total: int


# ─── Избранные компании ──────────────────────────────────────


class FavoriteCompanyItem(SchemaBase):
    """Элемент списка избранных компаний."""

    id: uuid.UUID
    company: CompanyShort
    created_at: datetime


class FavoriteCompanyListResponse(BaseModel):
    """Ответ на GET /favorites/companies."""

    items: list[FavoriteCompanyItem]
    total: int
