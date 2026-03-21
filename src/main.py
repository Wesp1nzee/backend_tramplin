from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import settings

from src.core.exceptions import setup_exception_handlers
from src.api.v1.endpoints.auth import router
from src.db.session import session_manager

# from src.utils.cache import cache_manager

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Управление жизненным циклом приложения:
    Инициализация ресурсов до старта и их очистка после остановки.
    """
    session_manager.init(settings.DATABASE_URL)

    # await cache_manager.connect(settings.VALKEY_URL)

    logger.info("Application started", env=settings.ENVIRONMENT, version="0.1.0")

    yield

    await session_manager.close()
    # await cache_manager.disconnect()
    logger.info("Application shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Tramplin API",
        description="Экосистема для студентов и работодателей 'Трамплин'",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.DEBUG else None,
        redoc_url=None,
    )

    # Middlewares
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # обработчиков кастомных исключений
    setup_exception_handlers(app)

    # Подключение роутеров (Версионирование v1)
    app.include_router(router, prefix=settings.API_V1_STR)

    return app


app = create_app()


# Эндпоинт для проверки здоровья (Health Check) для Docker/K8s
@app.get("/health", tags=["System"])
async def health_check() -> dict[str, str | bool]:
    return {
        "status": "healthy",
        "database": await session_manager.check_health(),
        # "cache": await cache_manager.check_health()
    }
