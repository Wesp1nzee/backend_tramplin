"""
Middleware для логирования HTTP запросов и ответов.
"""

import time
import uuid

from fastapi import Request, Response
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware для логирования всех HTTP запросов.
    """

    EXCLUDED_PATHS = {
        "/health",
        "/api/docs",
        "/api/redoc",
        "/api/openapi.json",
        "/favicon.ico",
    }

    SENSITIVE_HEADERS = {
        "authorization",
        "x-refresh-token",
        "cookie",
        "x-api-key",
    }

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if any(request.url.path.startswith(path) for path in self.EXCLUDED_PATHS):
            return await call_next(request)

        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        start_time = time.perf_counter()
        logger.bind(
            log_type="access",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            client_ip=self._get_client_ip(request),
        ).info("HTTP Request Started")

        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

            log_level = self._get_log_level(response.status_code)
            logger.bind(
                log_type="access",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
            ).log(log_level, "HTTP Request Completed")

            response.headers["X-Request-ID"] = request_id
            return response

        except Exception as e:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

            logger.exception(
                "HTTP Request Failed",
                extra={
                    "log_type": "access",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": 500,
                    "duration_ms": duration_ms,
                    "client_ip": self._get_client_ip(request),
                    "error": str(e),
                },
            )
            raise

    @staticmethod
    def _sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
        sanitized = {}
        for key, value in headers.items():
            if key.lower() in RequestLoggingMiddleware.SENSITIVE_HEADERS:
                sanitized[key] = "****"
            else:
                sanitized[key] = value
        return sanitized

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    @staticmethod
    def _get_log_level(status_code: int) -> str:
        if status_code >= 500:
            return "ERROR"
        elif status_code >= 400:
            return "WARNING"
        return "INFO"


class SlowRequestMiddleware(BaseHTTPMiddleware):
    """
    Middleware для логирования медленных запросов.
    """

    THRESHOLD_MS = 1000

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        start_time = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start_time) * 1000

        if duration_ms > self.THRESHOLD_MS:
            logger.warning(
                "Slow Request Detected",
                extra={
                    "log_type": "performance",
                    "request_id": getattr(request.state, "request_id", None),
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round(duration_ms, 2),
                    "threshold_ms": self.THRESHOLD_MS,
                },
            )

        return response
