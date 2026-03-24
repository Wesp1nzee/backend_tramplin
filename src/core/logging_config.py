"""
Конфигурация логирования с использованием Loguru.
"""

import re
import sys
from pathlib import Path
from typing import Any

from loguru import Logger, logger

from src.core.config import settings


def mask_sensitive_data(record: dict[str, Any]) -> bool:
    """
    Маскирует чувствительные данные в логах.
    """
    message = record["message"]
    sensitive_patterns = [
        "password",
        "token",
        "secret",
        "authorization",
        "credential",
        "api_key",
        "access_token",
        "refresh_token",
    ]

    for pattern in sensitive_patterns:
        if pattern.lower() in message.lower():
            message = re.sub(
                rf'({pattern}[=:]\s*)(["\']?)([^"\'\s,}}]+)(\2)',
                r"\1\2****\4",
                message,
                flags=re.IGNORECASE,
            )

    record["message"] = message
    return True


def format_log(record: dict[str, Any]) -> str:
    """
    Форматирование лога для консольного вывода.
    """
    extra = record.get("extra", {})

    log_parts = [
        f"<green>{record['time'].strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}</green>",
        "|",
        f"<level>{record['level'].name: <8}</level>",
        "|",
        f"<cyan>{record['name']}</cyan>:<cyan>{record['function']}</cyan>:<cyan>{record['line']}</cyan>",
        "|",
    ]

    request_id = extra.get("request_id")
    if request_id:
        log_parts.append(f"<magenta>[{request_id[:8]}]</magenta>")
        log_parts.append("|")

    if extra.get("log_type") == "access":
        method = extra.get("method", "???")
        path = extra.get("path", "???")
        status_code = extra.get("status_code")
        duration_ms = extra.get("duration_ms")

        if status_code:
            if status_code >= 500:
                status_display = f"<red>{status_code}</red>"
            elif status_code >= 400:
                status_display = f"<yellow>{status_code}</yellow>"
            else:
                status_display = f"<green>{status_code}</green>"
        else:
            status_display = ""

        if duration_ms:
            if duration_ms > 1000:
                latency_display = f"<red>{duration_ms}ms</red>"
            elif duration_ms > 500:
                latency_display = f"<yellow>{duration_ms}ms</yellow>"
            else:
                latency_display = f"<green>{duration_ms}ms</green>"
        else:
            latency_display = ""

        http_info = f"<magenta>{method}</magenta> <white>{path}</white>"
        if status_display:
            http_info += f" | {status_display}"
        if latency_display:
            http_info += f" | {latency_display}"

        log_parts.append(http_info)
        log_parts.append("|")

    # Добавляем сообщение
    log_parts.append(f"<level>{record['message']}</level>")

    return " ".join(log_parts) + "\n"


def format_json(record: dict[str, Any]) -> str:
    """
    JSON формат для продакшена.
    """
    import json

    log_entry = {
        "timestamp": record["time"].isoformat(),
        "level": record["level"].name,
        "logger": record["name"],
        "function": record["function"],
        "line": record["line"],
        "message": record["message"],
        "extra": record.get("extra", {}),
    }

    if record["exception"]:
        log_entry["exception"] = {
            "type": str(record["exception"].type),
            "value": str(record["exception"].value),
            "traceback": "".join(record["exception"].traceback.format()),
        }

    return json.dumps(log_entry, ensure_ascii=False, default=str) + "\n"


def setup_logging() -> None:
    """
    Инициализация логирования для приложения.
    """
    logger.remove()

    log_level = "DEBUG" if settings.DEBUG else "INFO"

    logger.add(
        sys.stdout,
        format=format_log,  # type: ignore
        level=log_level,
        colorize=settings.DEBUG,
        filter=mask_sensitive_data,  # type: ignore
        backtrace=True,
        diagnose=settings.DEBUG,
    )

    if settings.ENVIRONMENT == "prod":
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)

        logger.add(
            log_dir / "app.log",
            format=format_json,  # type: ignore
            level="INFO",
            rotation="100 MB",
            retention="30 days",
            compression="zip",
            filter=mask_sensitive_data,  # type: ignore
            backtrace=True,
            diagnose=False,
        )

        logger.add(
            log_dir / "error.log",
            format=format_json,  # type: ignore
            level="ERROR",
            rotation="100 MB",
            retention="30 days",
            compression="zip",
            filter=mask_sensitive_data,  # type: ignore
            backtrace=True,
            diagnose=False,
        )

        logger.add(
            log_dir / "access.log",
            format=format_json,  # type: ignore
            level="INFO",
            rotation="100 MB",
            retention="14 days",
            compression="zip",
            filter=lambda record: record["extra"].get("log_type") == "access",
        )

    logger.info(
        "Logging initialized",
        environment=settings.ENVIRONMENT,
        debug=settings.DEBUG,
        log_level=log_level,
    )


def get_logger(name: str = __name__) -> Logger:
    """
    Получение инстанса логгера для модуля.
    """
    return logger.bind(name=name)


__all__ = ["setup_logging", "get_logger", "logger"]
