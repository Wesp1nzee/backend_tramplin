from collections.abc import AsyncGenerator

import fakeredis.aioredis
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from src.db.base import Base
from src.db.session import get_db
from src.main import app

app.state.limiter.enabled = False
TEST_DATABASE_URL = "postgresql+asyncpg://test_user:test_password@localhost:5433/test_tramplin?ssl=disable"


@pytest_asyncio.fixture(scope="session")
async def db_engine() -> AsyncGenerator[AsyncEngine]:
    """Создаёт движок БД один раз на все тесты."""
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    # Создаем сессию с автоматическим откатом, чтобы база всегда была чистой
    connection = await db_engine.connect()
    trans = await connection.begin()

    # join_transaction_mode="create_savepoint" позволяет делать commit внутри кода,
    # но на самом деле в базу ничего не запишется до конца теста
    session = AsyncSession(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")

    yield session

    await session.close()
    await trans.rollback()
    await connection.close()


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient]:
    # Важно: переопределяем зависимость именно той сессией, которую используем в фикстурах данных
    async def _override_get_db() -> AsyncGenerator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def fake_redis() -> AsyncGenerator[fakeredis.aioredis.FakeRedis]:
    """FakeRedis для изоляции кэша."""
    redis = fakeredis.aioredis.FakeRedis()
    yield redis
    await redis.aclose()
