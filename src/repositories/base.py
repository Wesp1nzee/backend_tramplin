from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.base import Base


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
        return await self.db.get(self.model, obj_id)

    async def get_all(self, *, limit: int = 100, offset: int = 0) -> list[ModelType]:
        """Получить список объектов с пагинацией."""
        result = await self.db.execute(select(self.model).limit(limit).offset(offset))
        return list(result.scalars().all())

    async def exists(self, obj_id: UUID) -> bool:
        """Проверить существование объекта по ID."""
        result = await self.db.execute(
            select(self.model.id).where(self.model.id == obj_id)  # type: ignore[attr-defined]
        )
        return result.scalar_one_or_none() is not None

    async def delete(self, obj: ModelType) -> None:
        """Удалить объект из БД."""
        await self.db.delete(obj)
        await self.db.commit()
