"""
Экспорт всех моделей для Alembic и импортов в других модулях.

Порядок импорта важен для корректного разрешения forward references в SQLAlchemy.
"""

from src.models.application import Application, EventRegistration
from src.models.company import Company, CompanyVerification
from src.models.enums import (
    ApplicationStatus,
    ContactStatus,
    EmploymentType,
    ExperienceLevel,
    MessageStatus,
    NotificationType,
    OpportunityStatus,
    OpportunityType,
    ReviewTarget,
    SkillCategory,
    UserRole,
    VerificationStatus,
    WorkFormat,
)
from src.models.messaging import Conversation, ConversationParticipant, Message, MessageAttachment
from src.models.notification import Notification, Review
from src.models.opportunity import Opportunity, OpportunitySkill, OpportunityTag, Tag
from src.models.skill import ProfileSkill, Skill
from src.models.social import Contact, Favorite, FavoriteCompany, Recommendation

# Базовые модели (без внешних зависимостей внутри пакета)
from src.models.user import Profile, User

__all__ = [
    # Enums
    "UserRole",
    "OpportunityType",
    "WorkFormat",
    "ExperienceLevel",
    "EmploymentType",
    "ApplicationStatus",
    "VerificationStatus",
    "ContactStatus",
    "NotificationType",
    "MessageStatus",
    "OpportunityStatus",
    "SkillCategory",
    "ReviewTarget",
    # Users
    "User",
    "Profile",
    # Skills
    "Skill",
    "ProfileSkill",
    # Companies
    "Company",
    "CompanyVerification",
    # Opportunities
    "Opportunity",
    "Tag",
    "OpportunityTag",
    "OpportunitySkill",
    # Applications
    "Application",
    "EventRegistration",
    # Social
    "Contact",
    "Favorite",
    "FavoriteCompany",
    "Recommendation",
    # Messaging
    "Conversation",
    "ConversationParticipant",
    "Message",
    "MessageAttachment",
    # Notifications & Reviews
    "Notification",
    "Review",
]
