import enum


class UserRole(enum.StrEnum):
    APPLICANT = "applicant"  # Соискатель
    EMPLOYER = "employer"  # Работодатель
    CURATOR = "curator"  # Куратор (Админ)


class OpportunityType(enum.StrEnum):
    VACANCY = "vacancy"  # Вакансия (Junior+)
    INTERNSHIP = "internship"  # Стажировка
    MENTORING = "mentoring"  # Менторская программа
    EVENT = "event"  # Карьерное мероприятие (хакатон, день открытых дверей)


class WorkFormat(enum.StrEnum):
    OFFICE = "office"  # Офис
    HYBRID = "hybrid"  # Гибрид
    REMOTE = "remote"  # Удалённо
    ONLINE = "online"  # Онлайн (для мероприятий)


class ExperienceLevel(enum.StrEnum):
    INTERN = "intern"  # Стажёр
    JUNIOR = "junior"  # Junior
    MIDDLE = "middle"  # Middle
    SENIOR = "senior"  # Senior
    LEAD = "lead"  # Lead/Principal


class EmploymentType(enum.StrEnum):
    FULL_TIME = "full_time"  # Полная занятость
    PART_TIME = "part_time"  # Частичная занятость
    PROJECT = "project"  # Проектная работа
    VOLUNTEER = "volunteer"  # Волонтёрство


class ApplicationStatus(enum.StrEnum):
    PENDING = "pending"  # На рассмотрении
    VIEWED = "viewed"  # Просмотрен работодателем
    ACCEPTED = "accepted"  # Принят
    REJECTED = "rejected"  # Отклонён
    RESERVE = "reserve"  # В резерве
    WITHDRAWN = "withdrawn"  # Отозван соискателем


class VerificationStatus(enum.StrEnum):
    PENDING = "pending"  # Ожидает верификации
    APPROVED = "approved"  # Верифицирован
    REJECTED = "rejected"  # Отклонён
    REVOKED = "revoked"  # Верификация отозвана


class ContactStatus(enum.StrEnum):
    PENDING = "pending"  # Запрос отправлен
    ACCEPTED = "accepted"  # Принят
    REJECTED = "rejected"  # Отклонён
    BLOCKED = "blocked"  # Заблокирован


class NotificationType(enum.StrEnum):
    APPLICATION_STATUS = "application_status"  # Изменение статуса отклика
    NEW_APPLICATION = "new_application"  # Новый отклик на вакансию
    CONTACT_REQUEST = "contact_request"  # Запрос в контакты
    CONTACT_ACCEPTED = "contact_accepted"  # Запрос принят
    NEW_MESSAGE = "new_message"  # Новое сообщение
    OPPORTUNITY_EXPIRED = "opportunity_expired"  # Вакансия истекает
    COMPANY_VERIFIED = "company_verified"  # Компания верифицирована
    RECOMMENDATION = "recommendation"  # Рекомендация от контакта
    SYSTEM = "system"  # Системное уведомление


class MessageStatus(enum.StrEnum):
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"


class OpportunityStatus(enum.StrEnum):
    DRAFT = "draft"  # Черновик (не опубликована)
    ACTIVE = "active"  # Активна
    PAUSED = "paused"  # Приостановлена
    CLOSED = "closed"  # Закрыта
    PLANNED = "planned"  # Запланирована (будет опубликована)


class SkillCategory(enum.StrEnum):
    LANGUAGE = "language"  # Языки программирования (Python, Java, Go...)
    FRAMEWORK = "framework"  # Фреймворки (FastAPI, React, Spring...)
    DATABASE = "database"  # Базы данных (PostgreSQL, Redis, MongoDB...)
    DEVOPS = "devops"  # DevOps (Docker, K8s, CI/CD...)
    CLOUD = "cloud"  # Облачные технологии (AWS, GCP, Azure...)
    MOBILE = "mobile"  # Мобильная разработка
    AI_ML = "ai_ml"  # AI/ML (PyTorch, TensorFlow, sklearn...)
    DESIGN = "design"  # Дизайн (Figma, Photoshop...)
    MANAGEMENT = "management"  # Менеджмент (Scrum, Agile...)
    SOFT = "soft"  # Мягкие навыки
    OTHER = "other"  # Прочее


class ReviewTarget(enum.StrEnum):
    COMPANY = "company"
    OPPORTUNITY = "opportunity"
