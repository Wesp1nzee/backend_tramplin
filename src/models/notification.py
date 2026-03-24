"""
Уведомления и отзывы.

Notification — система уведомлений (в приложении).
Review       — отзывы соискателей о компаниях и возможностях.

Авторское решение по уведомлениям:
  Хранятся в БД для истории и badge-счётчика (in-app).
  Дублируются через WebSocket (FastAPI + Redis pub/sub) для real-time.
  Email-уведомления отправляются через очередь RabbitMQ (уже есть в конфиге).

Авторское решение по отзывам:
  Соискатели могут оставлять отзывы о компаниях после завершения стажировки/работы.
  Отзывы проходят модерацию куратора перед публикацией.
  Это повышает доверие к платформе и помогает другим соискателям.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, TimestampMixin, UUIDMixin
from src.models.enums import NotificationType, ReviewTarget

if TYPE_CHECKING:
    from src.models.company import Company
    from src.models.user import User


class Notification(Base, UUIDMixin, TimestampMixin):
    """
    In-app уведомление для пользователя.

    Типы уведомлений:
      - APPLICATION_STATUS: Работодатель изменил статус вашего отклика
      - NEW_APPLICATION:    Новый отклик на вашу вакансию
      - CONTACT_REQUEST:    Пользователь X хочет добавить вас в контакты
      - CONTACT_ACCEPTED:   X принял ваш запрос в контакты
      - NEW_MESSAGE:        Новое сообщение от X
      - OPPORTUNITY_EXPIRED: Ваша вакансия закрывается через 3 дня
      - COMPANY_VERIFIED:  Ваша компания верифицирована
      - RECOMMENDATION:    X рекомендует вам вакансию Y
      - SYSTEM:            Системное объявление от администрации
    """

    __tablename__ = "notifications"

    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    type: Mapped[NotificationType] = mapped_column(Enum(NotificationType, native_enum=False))

    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # Полезная нагрузка для построения ссылки в UI
    # Пример: {"type": "application", "id": "uuid", "url": "/applications/uuid"}
    payload: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict, server_default="{}")

    # Relationships
    recipient: Mapped[User] = relationship("User", back_populates="notifications")

    __table_args__ = (
        Index("ix_notifications_recipient_unread", "recipient_id", "is_read"),
        Index("ix_notifications_type", "type"),
    )


class Review(Base, UUIDMixin, TimestampMixin):
    """
    Отзыв соискателя о компании или возможности.

    Публикуется только после модерации куратором.
    Один пользователь — один отзыв на одну компанию/вакансию.

    Авторское решение: рейтинги разбиты на субкатегории
    (атмосфера, карьерный рост, зарплата) для более детальной обратной связи.
    """

    __tablename__ = "reviews"

    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # Полиморфная связь: компания или вакансия
    target_type: Mapped[ReviewTarget] = mapped_column(Enum(ReviewTarget, native_enum=False), index=True)
    target_id: Mapped[uuid.UUID] = mapped_column(index=True)

    # Основной рейтинг (1-5)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)

    # Детальные рейтинги (только для компаний, 1-5 или NULL)
    rating_culture: Mapped[int | None] = mapped_column(Integer)  # Культура и атмосфера
    rating_career: Mapped[int | None] = mapped_column(Integer)  # Карьерный рост
    rating_salary: Mapped[int | None] = mapped_column(Integer)  # Зарплата и льготы
    rating_management: Mapped[int | None] = mapped_column(Integer)  # Менеджмент

    title: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    pros: Mapped[str | None] = mapped_column(Text)  # Плюсы
    cons: Mapped[str | None] = mapped_column(Text)  # Минусы

    # Верификация прохождения стажировки (необязательно)
    employment_period: Mapped[str | None] = mapped_column(Text)  # "2024-01 / 2024-06"

    # Модерация
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False)
    moderated_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    moderation_comment: Mapped[str | None] = mapped_column(Text)

    # Relationships
    author: Mapped[User] = relationship("User", back_populates="reviews", foreign_keys=[author_id])
    company: Mapped[Company | None] = relationship(
        "Company",
        primaryjoin="and_(Review.target_id == Company.id, Review.target_type == 'company')",
        foreign_keys=[target_id],
        viewonly=True,
        overlaps="reviews",
    )

    __table_args__ = (
        Index("ix_reviews_target", "target_type", "target_id", "is_published"),
        Index("ix_reviews_author_target", "author_id", "target_type", "target_id", unique=True),
    )
