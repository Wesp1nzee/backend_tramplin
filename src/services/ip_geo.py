"""
Сервис IP-геолокации через Dadata iplocate/address.

Логика:
  1. Проверяем Redis-кэш по ключу ip_geo:{ip} (TTL 24 часа)
  2. Если нет — запрашиваем Dadata
  3. Кэшируем результат
  4. При любой ошибке — возвращаем default_city (Москва)

Dadata iplocate docs:
  POST https://suggestions.dadata.ru/suggestions/api/4_1/rs/iplocate/address
  Body: {"ip": "46.226.227.20"}
  Response: {"location": {"data": {"city": "Краснодар", ...}}}
"""

import json
import logging
from typing import cast

import httpx
import redis.asyncio as redis

from src.core.config import settings

logger = logging.getLogger(__name__)

DADATA_IPLOCATE_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/iplocate/address"

# Redis TTL для кэша геолокации — 24 часа
IP_GEO_TTL = 60 * 60 * 24
IP_GEO_PREFIX = "ip_geo:"

# IP-адреса, которые нельзя геолоцировать (локальные, приватные)
_PRIVATE_IP_PREFIXES = (
    "127.",
    "10.",
    "192.168.",
    "172.16.",
    "172.17.",
    "172.18.",
    "172.19.",
    "172.20.",
    "172.21.",
    "172.22.",
    "172.23.",
    "172.24.",
    "172.25.",
    "172.26.",
    "172.27.",
    "172.28.",
    "172.29.",
    "172.30.",
    "172.31.",
    "::1",
    "localhost",
)


def _is_private_ip(ip: str) -> bool:
    """Проверяет, является ли IP локальным/приватным."""
    return any(ip.startswith(prefix) for prefix in _PRIVATE_IP_PREFIXES)


class IPGeolocationService:
    """
    Определяет город пользователя по IP через Dadata.

    Инжектируется через DI с уже существующим Redis-соединением.
    При недоступности Redis или Dadata — молча возвращает default_city.
    """

    def __init__(self, redis: redis.Redis | None = None) -> None:
        self._redis = redis
        self._timeout = httpx.Timeout(5.0)  # Быстрый таймаут — не блокируем UX

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Token {settings.DADATA_API_KEY}",
            "X-Secret": settings.DADATA_SECRET_KEY,
        }

    async def get_city_by_ip(
        self,
        ip: str,
        *,
        default_city: str = "Москва",
    ) -> tuple[str, bool]:
        """
        Возвращает (city, from_ip) где from_ip=True если город определён по IP.

        Args:
            ip: IP-адрес клиента
            default_city: Город по умолчанию если определить не удалось

        Returns:
            tuple[str, bool]: (название_города, определён_по_ip)
        """
        if _is_private_ip(ip):
            logger.debug("Private IP %s, using default city: %s", ip, default_city)
            return default_city, False

        cached = await self._get_from_cache(ip)
        if cached is not None:
            logger.debug("IP geo cache hit for %s: %s", ip, cached)
            return cached, True

        city = await self._fetch_from_dadata(ip)
        if city is None:
            logger.debug("Dadata returned no city for IP %s, using default: %s", ip, default_city)
            return default_city, False

        await self._set_cache(ip, city)

        logger.debug("IP geo resolved %s → %s", ip, city)
        return city, True

    async def _get_from_cache(self, ip: str) -> str | None:
        """Читает город из Redis. Возвращает None при любой ошибке."""
        if self._redis is None:
            return None
        try:
            key = f"{IP_GEO_PREFIX}{ip}"
            value = await self._redis.get(key)
            if value:
                data = json.loads(value)
                return cast(str | None, data.get("city"))
        except Exception as e:
            logger.warning("Redis cache read failed for IP geo: %s", e)
        return None

    async def _set_cache(self, ip: str, city: str) -> None:
        """Записывает город в Redis. При ошибке — не падает."""
        if self._redis is None:
            return
        try:
            key = f"{IP_GEO_PREFIX}{ip}"
            await self._redis.setex(key, IP_GEO_TTL, json.dumps({"city": city}))
        except Exception as e:
            logger.warning("Redis cache write failed for IP geo: %s", e)

    async def _fetch_from_dadata(self, ip: str) -> str | None:
        """
        Делает запрос к Dadata iplocate/address.

        Returns:
            Название города или None если не удалось определить.
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    DADATA_IPLOCATE_URL,
                    json={"ip": ip, "language": "ru"},
                    headers=self._headers,
                )
                response.raise_for_status()

            data = response.json()
            location = data.get("location")
            if not location:
                return None

            location_data = location.get("data", {})
            # Приоритет: city > settlement > region
            city = location_data.get("city") or location_data.get("settlement") or location_data.get("region_with_type")
            return cast(str | None, city)

        except httpx.TimeoutException:
            logger.warning("Dadata iplocate timeout for IP %s", ip)
        except httpx.HTTPStatusError as e:
            logger.warning("Dadata iplocate HTTP error for IP %s: %s", ip, e.response.status_code)
        except Exception as e:
            logger.warning("Dadata iplocate unexpected error for IP %s: %s", ip, e)

        return None
