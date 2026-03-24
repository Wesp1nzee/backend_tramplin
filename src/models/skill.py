"""
Модели навыков (Skills).

Вынесены в отдельную таблицу по требованию:
- Единый глобальный каталог навыков/технологий платформы
- Связь many-to-many с профилями соискателей
- Связь many-to-many с вакансиями через OpportunitySkill
- Кураторы и работодатели могут добавлять новые теги в каталог
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, TimestampMixin, UUIDMixin
from src.models.enums import SkillCategory

if TYPE_CHECKING:
    from src.models.opportunity import OpportunitySkill
    from src.models.user import Profile


class Skill(Base, UUIDMixin, TimestampMixin):
    """
    Глобальный каталог навыков и технологий.

    Стартовый список формируется разработчиком на основе
    популярных IT-специальностей. Кураторы и работодатели
    могут добавлять новые навыки в каталог.
    """

    __tablename__ = "skills"

    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    category: Mapped[SkillCategory] = mapped_column(
        Enum(SkillCategory, native_enum=False),
        default=SkillCategory.OTHER,
    )
    description: Mapped[str | None] = mapped_column(Text)
    icon_url: Mapped[str | None] = mapped_column(Text)

    # Системные навыки не могут быть удалены
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    # Флаг одобрения куратором (для навыков, добавленных работодателями)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    # Популярность — для сортировки в поиске
    usage_count: Mapped[int] = mapped_column(Integer, default=0)

    # Кто добавил навык (NULL = системный)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    # Relationships
    user_skills: Mapped[list[ProfileSkill]] = relationship("ProfileSkill", back_populates="skill")
    opportunity_skills: Mapped[list[OpportunitySkill]] = relationship("OpportunitySkill", back_populates="skill")

    __table_args__ = (
        Index("ix_skills_category", "category"),
        Index("ix_skills_is_approved", "is_approved"),
        Index("ix_skills_category_approved", "category", "is_approved"),
        Index("ix_skills_usage", "usage_count"),
    )

    def __repr__(self) -> str:
        return f"<Skill {self.name} ({self.category})>"


class ProfileSkill(Base, TimestampMixin):
    """
    Связь профиля соискателя с навыком (many-to-many).
    Дополнительные атрибуты: уровень владения навыком.
    """

    __tablename__ = "profile_skills"

    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True)
    skill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True)
    # Уровень владения (1=базовый, 2=средний, 3=продвинутый, 4=эксперт)
    proficiency_level: Mapped[int] = mapped_column(Integer, default=1)
    years_experience: Mapped[float | None] = mapped_column()

    # Relationships
    profile: Mapped[Profile] = relationship("Profile", back_populates="profile_skills")
    skill: Mapped[Skill] = relationship("Skill", back_populates="user_skills")

    __table_args__ = (
        Index("ix_profile_skills_profile", "profile_id"),
        Index("ix_profile_skills_skill", "skill_id"),
    )
