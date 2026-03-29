"""
Pydantic DTO-схемы для регистрации на мероприятия.

Используются только в API-слое — модели SQLAlchemy не проникают сюда.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.application import ApplicantProfileShort


class SchemaBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ─── Регистрация на мероприятие ───────────────────────────────


class EventRegistrationCreate(BaseModel):
    """Запрос на регистрацию на мероприятие."""

    # Можно добавить заметку при регистрации
    note: str | None = Field(None, max_length=500, description="Заметка к регистрации")


class EventRegistrationUpdate(BaseModel):
    """Запрос на обновление регистрации."""

    note: str | None = Field(None, max_length=500, description="Заметка к регистрации")


class EventRegistrationItem(SchemaBase):
    """Элемент списка участников мероприятия."""

    id: uuid.UUID
    profile: ApplicantProfileShort
    status: str  # confirmed, waitlist, cancelled
    check_in_code: str | None = None
    checked_in_at: datetime | None = None
    registered_at: datetime


class EventRegistrationListResponse(BaseModel):
    """Ответ на GET /events/{id}/participants."""

    items: list[EventRegistrationItem]
    total: int
    confirmed_count: int
    waitlist_count: int


class EventRegistrationResponse(SchemaBase):
    """Ответ на регистрацию/отмену регистрации."""

    id: uuid.UUID
    status: str
    message: str
    check_in_code: str | None = None
    event_id: uuid.UUID


# ─── Check-in ─────────────────────────────────────────────────


class EventCheckInRequest(BaseModel):
    """Запрос на отметку присутствия."""

    check_in_code: str = Field(..., min_length=6, max_length=10, description="Уникальный код для check-in")


class EventCheckInResponse(SchemaBase):
    """Ответ на check-in."""

    success: bool
    message: str
    profile_id: uuid.UUID
    checked_in_at: datetime


# ─── Информация о мероприятии для регистрации ─────────────────


class EventInfo(BaseModel):
    """Краткая информация о мероприятии для регистрации."""

    id: uuid.UUID
    title: str
    event_start_at: datetime | None = None
    event_end_at: datetime | None = None
    max_participants: int | None = None
    current_participants: int = 0
    available_spots: int | None = None
    user_registration_status: str | None = None  # registered, waitlist, none
