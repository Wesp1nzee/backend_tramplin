from collections.abc import AsyncGenerator

import fakeredis.aioredis
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
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
    """Создаёт сессию БД для каждого теста + очистка данных."""
    async_session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    session = async_session()
    try:
        await session.execute(text("TRUNCATE TABLE users, companies RESTART IDENTITY CASCADE"))
        await session.commit()
        yield session
    finally:
        await session.close()


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient]:
    """Тестовый клиент с переопределённой сессией БД."""

    async def _override_get_db() -> AsyncGenerator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    app.state.limiter.enabled = False

    limiter = app.state.limiter
    if hasattr(limiter, "_storage") and hasattr(limiter._storage, "storage"):
        limiter._storage.storage.clear()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def fake_redis() -> AsyncGenerator[fakeredis.aioredis.FakeRedis]:
    """FakeRedis для изоляции кэша."""
    redis = fakeredis.aioredis.FakeRedis()
    yield redis
    await redis.aclose()
