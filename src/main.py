from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.responses import Response

from src.api.v1.endpoints.auth import router as auth_router

# from src.api.v1.endpoints.companies import router as companies_router
from src.api.v1.endpoints.users import router as users_router
from src.core.config import settings
from src.core.exceptions import setup_exception_handlers
from src.core.init_data import create_default_admin
from src.db.session import session_manager
from src.utils.cache import token_blacklist
from src.utils.rate_limiter import limiter

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Управление жизненным циклом приложения:
    Инициализация ресурсов до старта и их очистка после остановки.
    """
    session_manager.init(settings.DATABASE_URL)

    await create_default_admin(session_manager)

    await token_blacklist.connect(settings.REDIS_URL)

    logger.info("Application started", env=settings.ENVIRONMENT, version="0.1.0")

    yield

    await token_blacklist.disconnect()
    await session_manager.close()
    logger.info("Application shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Tramplin API",
        description="Экосистема для студентов и работодателей 'Трамплин'",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.ENABLE_DOCS else None,
        redoc_url="/api/redoc" if settings.ENABLE_DOCS else None,
        openapi_url="/api/openapi.json" if settings.ENABLE_DOCS else None,
    )

    app.state.limiter = limiter
    if settings.ENABLE_RATE_LIMITING:
        app.add_exception_handler(
            RateLimitExceeded,
            _rate_limit_exceeded_handler,  # type: ignore[arg-type]
        )

    # Middlewares
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Refresh-Token"],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )

    @app.middleware("http")
    async def set_secure_headers(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    setup_exception_handlers(app)

    app.include_router(auth_router, prefix=settings.API_V1_STR)
    # app.include_router(companies_router, prefix=settings.API_V1_STR)
    app.include_router(users_router, prefix=settings.API_V1_STR)

    return app


app = create_app()


@app.get("/health", tags=["System"])
async def health_check() -> dict[str, str | bool]:
    return {
        "status": "healthy",
        "database": await session_manager.check_health(),
        "cache": await token_blacklist.check_health(),
    }
