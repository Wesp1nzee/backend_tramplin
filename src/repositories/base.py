from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import RepositoryError
from src.db.base import Base

logger = structlog.get_logger()


class BaseRepository[ModelType: Base]:
    """
    Базовый репозиторий с универсальными CRUD-операциями.

    Наследники указывают атрибут `model` и добавляют
    только специфичные для своей сущности запросы.

    Пример:
        class UserRepository(BaseRepository[User]):
            model = User
    """

    model: type[ModelType]

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, obj_id: UUID) -> ModelType | None:
        """Получить объект по первичному ключу."""
        try:
            return await self.db.get(self.model, obj_id)
        except SQLAlchemyError as e:
            logger.error(f"Database error while getting {self.model.__name__}", error=str(e))
            raise RepositoryError() from e

    async def get_all(self, *, limit: int = 100, offset: int = 0) -> list[ModelType]:
        """Получить список объектов с пагинацией."""
        try:
            result = await self.db.execute(select(self.model).limit(limit).offset(offset))
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(f"Database error while getting all {self.model.__name__}", error=str(e))
            raise RepositoryError() from e

    async def exists(self, obj_id: UUID) -> bool:
        """Проверить существование объекта по ID."""
        try:
            result = await self.db.execute(
                select(self.model.id).where(self.model.id == obj_id)  # type: ignore[attr-defined]
            )
            return result.scalar_one_or_none() is not None
        except SQLAlchemyError as e:
            logger.error("Database error while checking existence", error=str(e))
            raise RepositoryError() from e

    async def delete(self, obj: ModelType) -> None:
        """Удалить объект из БД."""
        try:
            await self.db.delete(obj)
            await self.db.commit()
        except SQLAlchemyError as e:
            logger.error(f"Database error while deleting {self.model.__name__}", error=str(e))
            await self.db.rollback()
            raise RepositoryError() from e
