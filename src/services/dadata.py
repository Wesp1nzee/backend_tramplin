"""
Сервис верификации компаний через Dadata API.

Используется при регистрации работодателя:
  1. Фронтенд отправляет ИНН → POST /api/v1/companies/verify-inn
  2. Сервис делает запрос к Dadata findById/party
  3. Возвращает данные компании (название, адрес, статус) или 404

Dadata API: https://dadata.ru/api/find-party/
Ключи берутся из settings.DADATA_API_KEY / settings.DADATA_SECRET_KEY
"""

from typing import Any

import httpx
import structlog

from src.core.config import settings
from src.core.exceptions import AppError, ExternalServiceError
from src.schemas.company import InnLookupResult

logger = structlog.get_logger()

DADATA_FIND_BY_ID_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party"


class InnNotFoundError(AppError):
    status_code = 404
    detail = "Company with this INN not found or does not exist"
    error_code = "INN_NOT_FOUND"


class InnCompanyLiquidatedError(AppError):
    status_code = 422
    detail = "Company with this INN is liquidated or bankrupt"
    error_code = "INN_COMPANY_LIQUIDATED"


class DadataService:
    """
    Клиент для Dadata API.

    Используем httpx.AsyncClient для неблокирующих запросов.
    Таймаут 10 сек — Dadata обычно отвечает быстро,
    но при деградации не хотим висеть долго.
    """

    def __init__(self) -> None:
        self._api_key = settings.DADATA_API_KEY
        self._secret_key = settings.DADATA_SECRET_KEY
        self._timeout = httpx.Timeout(10.0)

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Token {self._api_key}",
            "X-Secret": self._secret_key,
        }

    async def find_company_by_inn(self, inn: str) -> InnLookupResult:
        """
        Ищет компанию или ИП по ИНН через Dadata findById/party.

        Args:
            inn: ИНН компании (10 цифр) или ИП (12 цифр)

        Returns:
            InnLookupResult: Найденные данные компании

        Raises:
            InnNotFoundError:         ИНН не найден в реестре
            InnCompanyLiquidatedError: Компания ликвидирована / банкрот
            ExternalServiceError:     Dadata недоступна
        """
        payload = {
            "query": inn,
            "count": 1,
            "branch_type": "MAIN",  # только головная организация
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    DADATA_FIND_BY_ID_URL,
                    json=payload,
                    headers=self._headers,
                )
                response.raise_for_status()
        except httpx.TimeoutException as e:
            logger.error("Dadata API timeout", inn=inn)
            raise ExternalServiceError("Dadata API timeout. Please try again later.") from e
        except httpx.HTTPStatusError as e:
            logger.error(
                "Dadata API HTTP error",
                inn=inn,
                status_code=e.response.status_code,
                body=e.response.text,
            )
            raise ExternalServiceError(
                f"Dadata API returned error: {e.response.status_code}"
            ) from e
        except httpx.RequestError as e:
            logger.error("Dadata API connection error", inn=inn, error=str(e))
            raise ExternalServiceError("Cannot connect to Dadata API") from e

        data = response.json()
        suggestions: list[dict[str, Any]] = data.get("suggestions", [])

        if not suggestions:
            logger.info("INN not found in Dadata", inn=inn)
            raise InnNotFoundError()

        suggestion = suggestions[0]
        party_data: dict[str, Any] = suggestion.get("data", {})

        # Проверяем статус компании
        state: dict[str, Any] = party_data.get("state", {})
        status_value: str = state.get("status", "")

        if status_value in ("LIQUIDATED", "BANKRUPT"):
            logger.info(
                "Company is liquidated or bankrupt",
                inn=inn,
                status=status_value,
            )
            raise InnCompanyLiquidatedError()

        return self._parse_suggestion(suggestion)

    def _parse_suggestion(self, suggestion: dict[str, Any]) -> InnLookupResult:
        """
        Маппит ответ Dadata → внутренний DTO InnLookupResult.

        Берём только поля, нужные для верификации и предзаполнения формы.
        """
        data: dict[str, Any] = suggestion.get("data", {})
        state: dict[str, Any] = data.get("state", {})
        name: dict[str, Any] = data.get("name", {})
        address: dict[str, Any] = data.get("address", {})
        management: dict[str, Any] = data.get("management") or {}
        opf: dict[str, Any] = data.get("opf", {})

        is_individual = data.get("type") == "INDIVIDUAL"

        if is_individual:
            display_name = suggestion.get("value", "")
        else:
            display_name = (
                name.get("short_with_opf")
                or name.get("full_with_opf")
                or suggestion.get("value", "")
            )

        return InnLookupResult(
            inn=data.get("inn", ""),
            kpp=data.get("kpp"),
            ogrn=data.get("ogrn"),
            full_name=name.get("full_with_opf") or suggestion.get("unrestricted_value", ""),
            short_name=display_name,
            legal_form=opf.get("short"),
            is_individual=is_individual,
            status=state.get("status", "ACTIVE"),
            registration_date=state.get("registration_date"),
            address=address.get("value"),
            city=self._extract_city(address),
            ceo_name=management.get("name"),
            ceo_post=management.get("post"),
            okved=data.get("okved"),
            branch_type=data.get("branch_type", "MAIN"),
        )

    @staticmethod
    def _extract_city(address: dict[str, Any]) -> str | None:
        """Вытаскивает название города из гранулярного адреса Dadata."""
        addr_data: dict[str, Any] = address.get("data") or {}
        return (
            addr_data.get("city")
            or addr_data.get("settlement")
            or addr_data.get("region_with_type")
        )


# Синглтон — переиспользуется между запросами
dadata_service = DadataService()
