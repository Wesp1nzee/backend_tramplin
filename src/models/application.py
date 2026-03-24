"""
Модель откликов (Applications).

Application — отклик соискателя на вакансию/стажировку/менторство.
              Для мероприятий используется отдельная модель EventRegistration.

Статусная машина откликов:
  PENDING → VIEWED → ACCEPTED / REJECTED / RESERVE
  Соискатель может WITHDRAWN на любом этапе до ACCEPTED.

Авторское решение:
  Хранение истории изменений статуса в JSONB-колонке status_history
  позволяет отображать timeline в ЛК работодателя без JOIN с audit-таблицей.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, TimestampMixin, UUIDMixin
from src.models.enums import ApplicationStatus

if TYPE_CHECKING:
    from src.models.opportunity import Opportunity
    from src.models.user import Profile


class Application(Base, UUIDMixin, TimestampMixin):
    """Отклик соискателя на карточку возможности."""

    __tablename__ = "applications"

    opportunity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), index=True)
    applicant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), index=True)

    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus, native_enum=False),
        default=ApplicationStatus.PENDING,
    )

    # Сопроводительное письмо
    cover_letter: Mapped[str | None] = mapped_column(Text)
    # Ссылка на резюме в момент отклика (снапшот, чтобы не менялось ретроспективно)
    cv_url_snapshot: Mapped[str | None] = mapped_column(Text)

    # Комментарий работодателя (виден соискателю только при ACCEPTED/REJECTED)
    employer_comment: Mapped[str | None] = mapped_column(Text)
    # Внутренняя заметка работодателя (не видна соискателю)
    employer_note: Mapped[str | None] = mapped_column(Text)

    # История изменений статуса для timeline в ЛК
    # [{"status": "viewed", "changed_at": "2025-...", "changed_by": "employer"}]
    status_history: Mapped[list[dict[str, str]]] = mapped_column(JSONB, default=list, server_default="[]")

    # Даты
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Избранное у работодателя (shortlist)
    is_shortlisted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # Relationships
    opportunity: Mapped[Opportunity] = relationship("Opportunity", back_populates="applications")
    applicant_profile: Mapped[Profile] = relationship("Profile", back_populates="applications")

    __table_args__ = (
        # Один соискатель — один отклик на одну вакансию
        UniqueConstraint("opportunity_id", "applicant_id", name="uq_application_once"),
        Index("ix_applications_status", "status"),
        Index("ix_applications_opportunity_status", "opportunity_id", "status"),
        Index("ix_applications_applicant_status", "applicant_id", "status"),
    )


class EventRegistration(Base, UUIDMixin, TimestampMixin):
    """
    Регистрация соискателя на карьерное мероприятие.
    Отделена от Application, т.к. имеет другую логику:
    нет статусной машины работодателя, есть лимит участников.
    """

    __tablename__ = "event_registrations"

    opportunity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), index=True)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), index=True)

    # Статус регистрации: confirmed / waitlist / cancelled
    status: Mapped[str] = mapped_column(Text, default="confirmed")
    # QR-код или уникальный код для офлайн-верификации
    check_in_code: Mapped[str | None] = mapped_column(Text, unique=True, index=True)
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    opportunity: Mapped[Opportunity] = relationship("Opportunity", back_populates="event_registrations")
    profile: Mapped[Profile] = relationship("Profile", back_populates="event_registrations")

    __table_args__ = (
        UniqueConstraint("opportunity_id", "profile_id", name="uq_event_registration_once"),
        Index("ix_event_reg_opportunity", "opportunity_id"),
    )
