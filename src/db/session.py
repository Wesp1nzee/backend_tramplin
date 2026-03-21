from collections.abc import AsyncGenerator

import structlog
from pydantic import PostgresDsn
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = structlog.get_logger()


class SessionManager:
    def __init__(self) -> None:
        self.engine: AsyncEngine | None = None
        self.session_maker: async_sessionmaker[AsyncSession] | None = None

    def init(self, db_url: PostgresDsn | str) -> None:
        """
        Инициализация движка с настройками для Highload.
        """
        self.engine = create_async_engine(
            str(db_url),
            echo=False,
            pool_size=20,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=1800,
            pool_pre_ping=True,
        )

        self.session_maker = async_sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )

    async def close(self) -> None:
        """Закрытие всех соединений при остановке приложения."""
        if self.engine:
            await self.engine.dispose()
            self.engine = None
            self.session_maker = None

    async def check_health(self) -> bool:
        """Проверка связи с БД для Health Check."""
        if self.session_maker is None:
            logger.error("Database session maker is not initialized")
            return False

        try:
            async with self.session_maker() as session:
                from sqlalchemy import text

                await session.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error("Database health check failed", error=str(e))
            return False


session_manager = SessionManager()


async def get_db() -> AsyncGenerator[AsyncSession]:
    """
    Dependency для FastAPI эндпоинтов.
    Гарантирует закрытие сессии после выполнения запроса.
    """
    if session_manager.session_maker is None:
        raise Exception("Database session manager is not initialized")

    async with session_manager.session_maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
