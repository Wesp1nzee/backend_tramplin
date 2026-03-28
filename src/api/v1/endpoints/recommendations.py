"""
Эндпоинты для системы рекомендаций.

Рекомендации позволяют соискателям рекомендовать вакансии своим профессиональным контактам.

Эндпоинты:
  - POST /api/v1/recommendations - Создать рекомендацию
  - GET /api/v1/recommendations/sent - Список отправленных рекомендаций
  - GET /api/v1/recommendations/received - Список полученных рекомендаций
  - PATCH /api/v1/recommendations/{id}/read - Отметить как прочитанную
"""

from typing import Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel

from src.api.v1.deps import get_current_user, get_recommendation_service
from src.models.user import User
from src.schemas.recommendation import (
    RecommendationReceivedItem,
    RecommendationReceivedListResponse,
    RecommendationSentItem,
    RecommendationSentListResponse,
)
from src.services.recommendation import RecommendationService

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])


class RecommendationCreateRequest(BaseModel):
    """Запрос на создание рекомендации."""

    recipient_id: str
    opportunity_id: str
    message: str | None = None


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Создать рекомендацию",
    description="Рекомендовать вакансию контакту. Требуется наличие принятой связи (Contact ACCEPTED).",
)
async def create_recommendation(
    data: RecommendationCreateRequest,
    current_user: User = Depends(get_current_user),
    recommendation_service: RecommendationService = Depends(get_recommendation_service),
) -> dict[str, Any]:
    """
    Создать рекомендацию вакансии контакту.

    Требования:
    - Отправитель и получатель не могут быть одним лицом
    - Между пользователями должна быть связь со статусом ACCEPTED
    - Вакансия должна быть ACTIVE
    - Получатель должен быть соискателем (APPLICANT)

    Создаёт уведомление для получателя типа RECOMMENDATION.
    """
    from uuid import UUID

    try:
        recipient_uuid = UUID(data.recipient_id)
        opportunity_uuid = UUID(data.opportunity_id)
    except ValueError as e:
        from src.core.exceptions import NotFoundError

        raise NotFoundError(detail="Invalid ID format") from e

    result = await recommendation_service.create_recommendation(
        sender_id=current_user.id,
        recipient_id=recipient_uuid,
        opportunity_id=opportunity_uuid,
        message=data.message,
    )

    return {
        "id": str(result["id"]),
        "recipient_id": str(result["recipient_id"]),
        "opportunity_id": str(result["opportunity_id"]),
        "message": result["message"],
        "is_read": result["is_read"],
    }


@router.get(
    "/sent",
    response_model=RecommendationSentListResponse,
    status_code=status.HTTP_200_OK,
    summary="Список отправленных рекомендаций",
    description="Получить список рекомендаций, отправленных текущим пользователем.",
)
async def get_sent_recommendations(
    limit: int = Query(default=50, ge=1, le=100, description="Лимит записей"),
    offset: int = Query(default=0, ge=0, description="Смещение"),
    current_user: User = Depends(get_current_user),
    recommendation_service: RecommendationService = Depends(get_recommendation_service),
) -> RecommendationSentListResponse:
    """
    Получить список отправленных рекомендаций.

    Возвращает пагинированный список рекомендаций,
    которые текущий пользователь отправил своим контактам.
    """
    recommendations, total = await recommendation_service.get_sent_recommendations(
        sender_id=current_user.id,
        limit=limit,
        offset=offset,
    )

    items = []
    for rec in recommendations:
        items.append(
            RecommendationSentItem(
                id=rec.id,
                recipient={
                    "id": rec.recipient.id,
                    "first_name": rec.recipient.first_name,
                    "last_name": rec.recipient.last_name,
                    "avatar_url": rec.recipient.avatar_url,
                }
                if rec.recipient
                else None,
                opportunity={
                    "id": rec.opportunity.id,
                    "type": rec.opportunity.type,
                    "title": rec.opportunity.title,
                    "work_format": rec.opportunity.work_format,
                    "employment_type": rec.opportunity.employment_type,
                    "experience_level": rec.opportunity.experience_level,
                    "city": rec.opportunity.city,
                    "salary_min": rec.opportunity.salary_min,
                    "salary_max": rec.opportunity.salary_max,
                    "salary_currency": rec.opportunity.salary_currency,
                }
                if rec.opportunity
                else None,
                message=rec.message,
                is_read=rec.is_read,
                created_at=rec.created_at,
            )
        )

    return RecommendationSentListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/received",
    response_model=RecommendationReceivedListResponse,
    status_code=status.HTTP_200_OK,
    summary="Список полученных рекомендаций",
    description="Получить список рекомендаций, полученных текущим пользователем.",
)
async def get_received_recommendations(
    limit: int = Query(default=50, ge=1, le=100, description="Лимит записей"),
    offset: int = Query(default=0, ge=0, description="Смещение"),
    current_user: User = Depends(get_current_user),
    recommendation_service: RecommendationService = Depends(get_recommendation_service),
) -> RecommendationReceivedListResponse:
    """
    Получить список полученных рекомендаций.

    Возвращает пагинированный список рекомендаций,
    которые текущий пользователь получил от своих контактов.
    """
    recommendations, total = await recommendation_service.get_received_recommendations(
        recipient_id=current_user.id,
        limit=limit,
        offset=offset,
    )

    items = []
    for rec in recommendations:
        items.append(
            RecommendationReceivedItem(
                id=rec.id,
                sender={
                    "id": rec.sender.id,
                    "first_name": rec.sender.first_name,
                    "last_name": rec.sender.last_name,
                    "avatar_url": rec.sender.avatar_url,
                }
                if rec.sender
                else None,
                opportunity={
                    "id": rec.opportunity.id,
                    "type": rec.opportunity.type,
                    "title": rec.opportunity.title,
                    "work_format": rec.opportunity.work_format,
                    "employment_type": rec.opportunity.employment_type,
                    "experience_level": rec.opportunity.experience_level,
                    "city": rec.opportunity.city,
                    "salary_min": rec.opportunity.salary_min,
                    "salary_max": rec.opportunity.salary_max,
                    "salary_currency": rec.opportunity.salary_currency,
                }
                if rec.opportunity
                else None,
                message=rec.message,
                is_read=rec.is_read,
                created_at=rec.created_at,
            )
        )

    return RecommendationReceivedListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch(
    "/{recommendation_id}/read",
    status_code=status.HTTP_200_OK,
    summary="Отметить рекомендацию как прочитанную",
    description="Отметить полученную рекомендацию как прочитанную.",
)
async def mark_recommendation_as_read(
    recommendation_id: str,
    current_user: User = Depends(get_current_user),
    recommendation_service: RecommendationService = Depends(get_recommendation_service),
) -> dict[str, Any]:
    """
    Отметить рекомендацию как прочитанную.

    Доступно только получателю рекомендации.
    """
    from uuid import UUID

    try:
        rec_uuid = UUID(recommendation_id)
    except ValueError as e:
        from src.core.exceptions import NotFoundError

        raise NotFoundError(detail="Invalid recommendation ID") from e

    result = await recommendation_service.mark_recommendation_as_read(
        recommendation_id=rec_uuid,
        user_id=current_user.id,
    )

    return {
        "id": str(result["id"]),
        "is_read": result["is_read"],
        "updated_at": result["updated_at"],
    }
