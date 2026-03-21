import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, TimestampMixin, UUIDMixin
from src.models.enums import UserRole


class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(Text, unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False), default=UserRole.APPLICANT, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # Отношение к профилю
    profile: Mapped[Profile] = relationship(
        "Profile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class Profile(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )

    first_name: Mapped[str] = mapped_column(Text, index=True)
    last_name: Mapped[str] = mapped_column(Text, index=True)
    middle_name: Mapped[str | None] = mapped_column(Text)

    university: Mapped[str | None] = mapped_column(Text)
    graduation_year: Mapped[int | None] = mapped_column()

    skills: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    social_links: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict, server_default="{}")

    privacy_settings: Mapped[dict[str, bool]] = mapped_column(
        JSONB,
        default=lambda: {"public_profile": True, "show_contacts": False, "show_github": True},
        server_default='{"public_profile": true, "show_contacts": false, "show_github": true}',
    )

    user: Mapped[User] = relationship("User", back_populates="profile")

    __table_args__ = (
        Index("ix_profiles_skills_gin", "skills", postgresql_using="gin"),
        Index("ix_profiles_privacy_gin", "privacy_settings", postgresql_using="gin"),
    )
