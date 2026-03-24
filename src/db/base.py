import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column


class Base(DeclarativeBase):
    ""

    "Базовый класс для всех моделей SQLAlchemy."

    pass


class TimestampMixin:
    """Миксин для добавления полей времени создания и обновления."""

    @declared_attr
    def created_at(self) -> Mapped[datetime]:
        return mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    @declared_attr
    def updated_at(self) -> Mapped[datetime]:
        return mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class UUIDMixin:
    """Миксин для использования UUID в качестве первичного ключа."""

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
