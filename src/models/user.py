"""
Модели пользователей и профилей.

User      — учётная запись (email + пароль + роль).
Profile   — расширенные данные соискателя (ФИО, вуз, навыки и т.д.).
            Skills вынесены в таблицу ProfileSkill (many-to-many через Skill).
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, TimestampMixin, UUIDMixin
from src.models.enums import UserRole

if TYPE_CHECKING:
    from src.models.application import Application, EventRegistration
    from src.models.company import Company
    from src.models.messaging import ConversationParticipant, Message
    from src.models.notification import Notification, Review
    from src.models.skill import ProfileSkill
    from src.models.social import Contact, Favorite, FavoriteCompany, Recommendation


class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(Text, unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False), default=UserRole.APPLICANT, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    profile: Mapped[Profile] = relationship(
        "Profile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    company: Mapped[Company] = relationship(
        "Company",
        back_populates="owner",
        uselist=False,
        cascade="all, delete-orphan",
        foreign_keys="Company.owner_id",
    )
    sent_messages: Mapped[list[Message]] = relationship(
        "Message", back_populates="sender", foreign_keys="Message.sender_id"
    )
    notifications: Mapped[list[Notification]] = relationship(
        "Notification", back_populates="recipient", cascade="all, delete-orphan"
    )
    # Контакты (профессиональная сеть, аналог friends)
    sent_contacts: Mapped[list[Contact]] = relationship(
        "Contact",
        back_populates="requester",
        foreign_keys="Contact.requester_id",
        cascade="all, delete-orphan",
    )
    received_contacts: Mapped[list[Contact]] = relationship(
        "Contact",
        back_populates="addressee",
        foreign_keys="Contact.addressee_id",
        cascade="all, delete-orphan",
    )
    # Избранные вакансии (для авторизованных)
    favorites: Mapped[list[Favorite]] = relationship(
        "Favorite", back_populates="user", cascade="all, delete-orphan"
    )
    favorite_companies: Mapped[list[FavoriteCompany]] = relationship(
        "FavoriteCompany", back_populates="user", cascade="all, delete-orphan"
    )
    reviews: Mapped[list[Review]] = relationship(
        "Review",
        back_populates="author",
        cascade="all, delete-orphan",
        foreign_keys="Review.author_id",
    )
    conversation_participants: Mapped[list[ConversationParticipant]] = relationship(
        "ConversationParticipant", back_populates="user", cascade="all, delete-orphan"
    )


class Profile(Base, UUIDMixin, TimestampMixin):
    """
    Профиль соискателя.

    Навыки (skills) хранятся в таблице ProfileSkill (many-to-many),
    что позволяет:
    - Фильтровать кандидатов по конкретным технологиям
    - Считать рейтинг навыков по платформе
    - Указывать уровень владения каждым навыком
    """

    __tablename__ = "profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )

    first_name: Mapped[str] = mapped_column(Text, index=True)
    last_name: Mapped[str] = mapped_column(Text, index=True)
    middle_name: Mapped[str | None] = mapped_column(Text)

    # Образование
    university: Mapped[str | None] = mapped_column(Text)
    faculty: Mapped[str | None] = mapped_column(Text)
    specialization: Mapped[str | None] = mapped_column(Text)
    graduation_year: Mapped[int | None] = mapped_column(Integer)
    # 1-6 для студентов, NULL для выпускников
    study_year: Mapped[int | None] = mapped_column(Integer)

    # Профессиональная информация
    headline: Mapped[str | None] = mapped_column(Text)  # "Python-разработчик | ML-энтузиаст"
    bio: Mapped[str | None] = mapped_column(Text)  # О себе
    avatar_url: Mapped[str | None] = mapped_column(Text)

    # Контакты и ссылки (хранятся как JSONB для гибкости)
    # Пример: {"github": "...", "linkedin": "...", "telegram": "..."}
    social_links: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict, server_default="{}")
    # Контактный телефон (скрывается настройками приватности)
    phone: Mapped[str | None] = mapped_column(Text)

    # Портфолио
    portfolio_url: Mapped[str | None] = mapped_column(Text)
    cv_url: Mapped[str | None] = mapped_column(Text)  # Загруженное резюме (PDF)

    # Настройки приватности:
    # public_profile    — профиль виден всем авторизованным (нетворкинг)
    # show_contacts     — контактные данные видны контактам
    # show_github       — GitHub ссылка видна всем
    # show_applications — история откликов видна контактам
    privacy_settings: Mapped[dict[str, bool]] = mapped_column(
        JSONB,
        default=lambda: {
            "public_profile": True,
            "show_contacts": False,
            "show_github": True,
            "show_applications": False,
        },
        server_default=(
            '{"public_profile": true, "show_contacts": false, '
            '"show_github": true, "show_applications": false}'
        ),
    )

    # Карьерные предпочтения (для умного матчинга)
    # Пример: {"opportunity_types": ["internship", "vacancy"], "work_formats": ["remote", "hybrid"]}
    career_preferences: Mapped[dict[str, str]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="profile")
    profile_skills: Mapped[list[ProfileSkill]] = relationship(
        "ProfileSkill", back_populates="profile", cascade="all, delete-orphan"
    )
    applications: Mapped[list[Application]] = relationship(
        "Application", back_populates="applicant_profile", cascade="all, delete-orphan"
    )
    # Рекомендации, которые получил пользователь от своих контактов
    received_recommendations: Mapped[list[Recommendation]] = relationship(
        "Recommendation",
        back_populates="recipient",
        foreign_keys="Recommendation.recipient_id",
        cascade="all, delete-orphan",
    )
    sent_recommendations: Mapped[list[Recommendation]] = relationship(
        "Recommendation",
        back_populates="sender",
        foreign_keys="Recommendation.sender_id",
        cascade="all, delete-orphan",
    )
    # Регистрации на мероприятия
    event_registrations: Mapped[list[EventRegistration]] = relationship(
        "EventRegistration", back_populates="profile", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_profiles_university", "university"),
        Index("ix_profiles_graduation_year", "graduation_year"),
        Index("ix_profiles_privacy_gin", "privacy_settings", postgresql_using="gin"),
        Index("ix_profiles_career_prefs_gin", "career_preferences", postgresql_using="gin"),
    )

    @property
    def full_name(self) -> str:
        parts = [self.last_name, self.first_name]
        if self.middle_name:
            parts.append(self.middle_name)
        return " ".join(parts)
