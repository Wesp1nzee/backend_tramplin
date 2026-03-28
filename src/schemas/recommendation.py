"""
Схемы для системы рекомендаций.

Recommendation - рекомендация вакансии от одного соискателя другому.
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.application import OpportunityShort


class SchemaBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RecommendationCreate(SchemaBase):
    """Запрос на создание рекомендации."""

    recipient_id: uuid.UUID = Field(..., description="ID получателя рекомендации (профиль)")
    opportunity_id: uuid.UUID = Field(..., description="ID рекомендуемой вакансии")
    message: str | None = Field(None, max_length=500, description="Опциональное сообщение")


class RecommendationProfileShort(SchemaBase):
    """Краткая информация о профиле в рекомендации."""

    id: uuid.UUID
    first_name: str
    last_name: str
    avatar_url: str | None = None


class RecommendationSentItem(SchemaBase):
    """Элемент списка отправленных рекомендаций."""

    id: uuid.UUID
    recipient: RecommendationProfileShort
    opportunity: OpportunityShort
    message: str | None = None
    is_read: bool = False
    created_at: datetime


class RecommendationReceivedItem(SchemaBase):
    """Элемент списка полученных рекомендаций."""

    id: uuid.UUID
    sender: RecommendationProfileShort
    opportunity: OpportunityShort
    message: str | None = None
    is_read: bool = False
    created_at: datetime


class RecommendationListResponse(SchemaBase):
    """Ответ списка рекомендаций с пагинацией."""

    items: list[Any]
    total: int
    limit: int
    offset: int


class RecommendationSentListResponse(SchemaBase):
    """Ответ списка отправленных рекомендаций."""

    items: list[RecommendationSentItem]
    total: int
    limit: int
    offset: int


class RecommendationReceivedListResponse(SchemaBase):
    """Ответ списка полученных рекомендаций."""

    items: list[RecommendationReceivedItem]
    total: int
    limit: int
    offset: int


class RecommendationResponse(SchemaBase):
    """Полный ответ рекомендации."""

    id: uuid.UUID
    sender: RecommendationProfileShort
    recipient: RecommendationProfileShort
    opportunity: OpportunityShort
    message: str | None = None
    is_read: bool = False
    created_at: datetime
    updated_at: datetime
