"""
Система личных сообщений (Direct Messaging).

Conversation          — диалог между двумя пользователями.
ConversationParticipant — участники диалога (всегда 2).
Message               — конкретное сообщение в диалоге.
MessageAttachment     — вложение к сообщению (файл/ссылка).

Архитектурное решение:
  Модель поддерживает переписку:
  - Работодатель ↔ Соискатель (основной кейс по ТЗ)
  - Куратор ↔ Работодатель (по вопросам верификации)
  - Куратор ↔ Соискатель (модерация)

  Conversation привязан к контексту (opportunity_id) — диалог
  может быть инициирован из карточки вакансии или из отклика.
  Это позволяет в UI показывать «Написать по вакансии X».

  Soft-delete сообщений: удалённые сообщения хранятся с флагом
  is_deleted, чтобы не ломать счётчики непрочитанных.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, TimestampMixin, UUIDMixin
from src.models.enums import MessageStatus

if TYPE_CHECKING:
    from src.models.user import User


class Conversation(Base, UUIDMixin, TimestampMixin):
    """
    Диалог между двумя пользователями.

    Опционально привязан к конкретной вакансии (opportunity_id),
    что позволяет фильтровать переписку в контексте найма.
    """

    __tablename__ = "conversations"

    # Контекст диалога (необязательно)
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="SET NULL"), index=True
    )

    # Денормализованные счётчики для быстрого рендера списка диалогов
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_message_preview: Mapped[str | None] = mapped_column(Text)  # Первые 100 символов

    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    participants: Mapped[list[ConversationParticipant]] = relationship(
        "ConversationParticipant",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    messages: Mapped[list[Message]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )

    __table_args__ = (Index("ix_conversations_last_message", "last_message_at"),)


class ConversationParticipant(Base, TimestampMixin):
    """
    Участник диалога.
    Хранит per-user метаданные: кол-во непрочитанных, muted и т.д.
    """

    __tablename__ = "conversation_participants"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )

    unread_count: Mapped[int] = mapped_column(Integer, default=0)
    is_muted: Mapped[bool] = mapped_column(Boolean, default=False)
    # Дата, до которой участник удалил историю (soft-clear)
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    conversation: Mapped[Conversation] = relationship("Conversation", back_populates="participants")
    user: Mapped[User] = relationship("User", back_populates="conversation_participants")  # noqa: F821

    __table_args__ = (
        Index("ix_conv_participants_user", "user_id"),
        Index("ix_conv_participants_unread", "user_id", "unread_count"),
    )


class Message(Base, UUIDMixin, TimestampMixin):
    """
    Сообщение в диалоге.

    Поддерживает текст, вложения (файлы, ссылки) и системные сообщения
    (например, «Работодатель изменил статус отклика на Принят»).
    """

    __tablename__ = "messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    content: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[MessageStatus] = mapped_column(
        Enum(MessageStatus, native_enum=False),
        default=MessageStatus.SENT,
    )

    # Тип сообщения: "text" | "system" | "file"
    message_type: Mapped[str] = mapped_column(Text, default="text")

    # Ответ на другое сообщение (threading)
    reply_to_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL")
    )

    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    conversation: Mapped[Conversation] = relationship("Conversation", back_populates="messages")
    sender: Mapped[User] = relationship(  # noqa: F821
        "User", back_populates="sent_messages", foreign_keys=[sender_id]
    )
    attachments: Mapped[list[MessageAttachment]] = relationship(
        "MessageAttachment", back_populates="message", cascade="all, delete-orphan"
    )
    reply_to: Mapped[Message | None] = relationship(
        "Message", remote_side="Message.id", foreign_keys=[reply_to_id]
    )

    __table_args__ = (
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
        # Частичный индекс для непрочитанных
        Index(
            "ix_messages_unread",
            "conversation_id",
            "status",
            postgresql_where="status != 'read' AND is_deleted = false",
        ),
        Index("ix_messages_status", "status"),
        Index("ix_messages_message_type", "message_type"),
        Index("ix_messages_is_deleted", "is_deleted"),
    )


class MessageAttachment(Base, UUIDMixin):
    """Вложение к сообщению: файл, изображение или ссылка."""

    __tablename__ = "message_attachments"

    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )

    # Тип вложения: "file" | "image" | "link"
    attachment_type: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str | None] = mapped_column(Text)
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int | None] = mapped_column(Integer)  # Байты
    mime_type: Mapped[str | None] = mapped_column(Text)

    message: Mapped[Message] = relationship("Message", back_populates="attachments")
