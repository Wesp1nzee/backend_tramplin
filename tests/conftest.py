import asyncio
from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.db.base import Base
from src.db.session import get_db
from src.main import app
from src.models.user import Profile, User

TEST_DATABASE_URL = (
    "postgresql+asyncpg://test_user:test_password@localhost:5433/test_tramplin?ssl=disable"
)


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop]:
    """Создаем единый event loop для всей тестовой сессии."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db_engine() -> AsyncGenerator[AsyncEngine]:
    engine = create_async_engine(
        TEST_DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=0,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture(scope="function", loop_scope="session")
async def db_session(db_engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    async_session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async with async_session() as session:
        async with session.begin():
            await session.execute(delete(Profile))
            await session.execute(delete(User))

        yield session

        await session.rollback()


@pytest_asyncio.fixture(scope="function", loop_scope="session")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient]:
    """
    Создает тестовый клиент с переопределенной сессией БД.
    """

    async def _override_get_db() -> AsyncGenerator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    if hasattr(app.state, "limiter"):
        app.state.limiter.enabled = False

    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
