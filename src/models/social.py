"""
Социальные модели платформы.

Contact        — профессиональная сеть контактов соискателей (аналог друзей).
Favorite       — избранные вакансии (авторизованных пользователей).
FavoriteCompany — избранные компании.
Recommendation — рекомендация вакансии от контакта.

Авторское решение по избранному для неавторизованных:
  Неавторизованные пользователи хранят избранное в localStorage браузера.
  При авторизации фронт отправляет список ID для синхронизации с БД.

Авторское решение по нетворкингу:
  Контакты видят карьерные интересы друг друга (career_preferences в Profile)
  и могут рекомендовать друг друга на вакансии через модель Recommendation.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, TimestampMixin, UUIDMixin
from src.models.enums import ContactStatus

if TYPE_CHECKING:
    from src.models.company import Company
    from src.models.opportunity import Opportunity
    from src.models.user import Profile, User


class Contact(Base, UUIDMixin, TimestampMixin):
    """
    Запрос на добавление в профессиональные контакты.

    Статусная машина:
      PENDING  → ACCEPTED (двусторонняя связь установлена)
      PENDING  → REJECTED (можно повторить через 30 дней)
      ACCEPTED → BLOCKED  (разрыв связи)
    """

    __tablename__ = "contacts"

    requester_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    addressee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    status: Mapped[ContactStatus] = mapped_column(
        Enum(ContactStatus, native_enum=False),
        default=ContactStatus.PENDING,
    )

    # Сообщение при запросе (опционально)
    message: Mapped[str | None] = mapped_column(Text)

    # Relationships
    requester: Mapped[User] = relationship("User", back_populates="sent_contacts", foreign_keys=[requester_id])
    addressee: Mapped[User] = relationship("User", back_populates="received_contacts", foreign_keys=[addressee_id])

    __table_args__ = (
        # Нельзя дважды отправить запрос одному человеку
        UniqueConstraint("requester_id", "addressee_id", name="uq_contact_pair"),
        Index("ix_contacts_status", "status"),
        Index("ix_contacts_addressee_status", "addressee_id", "status"),
    )


class Favorite(Base, UUIDMixin, TimestampMixin):
    """Избранная вакансия/стажировка/мероприятие авторизованного пользователя."""

    __tablename__ = "favorites"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), index=True)

    # Пользовательская заметка к сохранённой вакансии
    note: Mapped[str | None] = mapped_column(Text)

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="favorites")
    opportunity: Mapped[Opportunity] = relationship("Opportunity", back_populates="favorites")

    __table_args__ = (
        UniqueConstraint("user_id", "opportunity_id", name="uq_favorite_once"),
        Index("ix_favorites_user", "user_id"),
    )


class FavoriteCompany(Base, UUIDMixin, TimestampMixin):
    """Избранная компания — маркеры вакансий этой компании выделяются на карте."""

    __tablename__ = "favorite_companies"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="favorite_companies")
    company: Mapped[Company] = relationship("Company", back_populates="favorited_by")

    __table_args__ = (UniqueConstraint("user_id", "company_id", name="uq_fav_company_once"),)


class Recommendation(Base, UUIDMixin, TimestampMixin):
    """
    Рекомендация вакансии от одного соискателя другому (контакту).

    Авторское решение: соискатели-контакты могут рекомендовать
    друг друга на вакансии. Рекомендация создаёт нотификацию
    получателю и помечает отклик флагом is_recommended в Application.
    """

    __tablename__ = "recommendations"

    sender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), index=True)

    message: Mapped[str | None] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(default=False)

    # Relationships
    sender: Mapped[Profile] = relationship("Profile", back_populates="sent_recommendations", foreign_keys=[sender_id])
    recipient: Mapped[Profile] = relationship("Profile", back_populates="received_recommendations", foreign_keys=[recipient_id])
    opportunity: Mapped[Opportunity] = relationship("Opportunity", back_populates="recommendations")

    __table_args__ = (Index("ix_recommendations_recipient", "recipient_id", "is_read"),)
