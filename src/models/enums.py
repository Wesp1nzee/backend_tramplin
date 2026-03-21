import enum


class UserRole(enum.StrEnum):
    APPLICANT = "applicant"  # Соискатель
    EMPLOYER = "employer"  # Работодатель
    CURATOR = "curator"  # Куратор (Админ)
