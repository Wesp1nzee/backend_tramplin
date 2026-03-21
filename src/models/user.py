import enum
import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, TimestampMixin, UUIDMixin


class UserRole(enum.StrEnum):
    APPLICANT = "applicant"  # Соискатель
    EMPLOYER = "employer"  # Работодатель
    CURATOR = "curator"  # Куратор (Админ)


class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(Text, unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False), default=UserRole.APPLICANT, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    profile: Mapped[Profile] = relationship(
        "Profile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class Profile(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )

    # ФИО и образование
    first_name: Mapped[str] = mapped_column(Text, index=True)
    last_name: Mapped[str] = mapped_column(Text, index=True)
    middle_name: Mapped[str | None] = mapped_column(Text)

    university: Mapped[str | None] = mapped_column(Text)
    graduation_year: Mapped[int | None] = mapped_column()

    # Технические данные
    # Используем JSONB для эффективного поиска по навыкам в Highload
    skills: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    github_url: Mapped[str | None] = mapped_column(Text)

    # Настройки видимости (ТЗ: переключатели видимости профиля)
    # Пример: {"public_profile": true, "show_contacts": false}
    privacy_settings: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")

    user: Mapped[User] = relationship("User", back_populates="profile")
