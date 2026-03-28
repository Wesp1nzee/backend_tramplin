from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.responses import Response

from src.api.v1.endpoints.applications import applicant_router, employer_applications_router, employer_opportunities_router
from src.api.v1.endpoints.auth import router as auth_router
from src.api.v1.endpoints.companies import router as companies_router
from src.api.v1.endpoints.glossary import router as glossary_router
from src.api.v1.endpoints.opportunities import router as opportunities_router
from src.api.v1.endpoints.recommendations import router as recommendations_router
from src.api.v1.endpoints.uploads import router as uploads_router
from src.api.v1.endpoints.users import router as users_router
from src.core.config import settings
from src.core.exceptions import setup_exception_handlers
from src.core.init_data import create_default_admin
from src.core.logging_config import logger, setup_logging
from src.db.session import session_manager
from src.middleware.logging import RequestLoggingMiddleware, SlowRequestMiddleware
from src.models.seed_data import seed_skills_and_tags
from src.utils.cache import token_blacklist
from src.utils.rate_limiter import limiter


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Управление жизненным циклом приложения.
    """

    setup_logging()

    logger.info("Application starting up", env=settings.ENVIRONMENT, version="0.1.0")

    session_manager.init(settings.DATABASE_URL)
    await create_default_admin(session_manager)

    # Заполняем каталог навыков и тегов системными данными
    if session_manager.session_maker:
        async with session_manager.session_maker() as session:
            await seed_skills_and_tags(session)
            logger.info("Skills and tags seeded successfully")

    await token_blacklist.connect(settings.REDIS_URL)

    logger.info(
        "Application started successfully",
        database="connected",
        cache="connected",
        docs_enabled=settings.ENABLE_DOCS,
    )

    yield

    logger.info("Application shutting down")
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

    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(SlowRequestMiddleware)

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
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    setup_exception_handlers(app)
    app.include_router(applicant_router, prefix=settings.API_V1_STR)
    app.include_router(employer_opportunities_router, prefix=settings.API_V1_STR)
    app.include_router(employer_applications_router, prefix=settings.API_V1_STR)
    app.include_router(auth_router, prefix=settings.API_V1_STR)
    app.include_router(companies_router, prefix=settings.API_V1_STR)
    app.include_router(opportunities_router, prefix=settings.API_V1_STR)
    app.include_router(users_router, prefix=settings.API_V1_STR)
    app.include_router(glossary_router, prefix=settings.API_V1_STR)
    app.include_router(uploads_router, prefix=settings.API_V1_STR)
    app.include_router(recommendations_router, prefix=settings.API_V1_STR)

    logger.info(
        "API routers registered",
        routes=["applications", "auth", "companies", "glossary", "opportunities", "users", "uploads", "recommendations"],
    )

    return app


app = create_app()


@app.get("/health", tags=["System"])
async def health_check() -> dict[str, str | bool]:
    request_id = getattr(app, "request_id", None)
    logger.debug(
        "Health check requested",
        extra={"request_id": request_id},
    )

    db_health = await session_manager.check_health()
    cache_health = await token_blacklist.check_health()

    logger.info(
        "Health check completed",
        database=db_health,
        cache=cache_health,
        status="healthy" if db_health and cache_health else "degraded",
    )

    return {
        "status": "healthy" if db_health and cache_health else "degraded",
        "database": db_health,
        "cache": cache_health,
    }
