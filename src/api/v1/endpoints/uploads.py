"""
Эндпоинты для загрузки файлов (CV и медиа).

Предоставляет:
  - POST /api/v1/uploads/cv - Загрузка резюме (CV)
  - POST /api/v1/uploads/media - Загрузка медиа (логотипы, фото, видео)
"""

from fastapi import APIRouter, Depends, UploadFile, status

from src.api.v1.deps import RoleChecker, get_current_user
from src.models.enums import UserRole
from src.models.user import User
from src.schemas.upload import CVUploadResponse, MediaUploadResponse
from src.services.upload import UploadService

router = APIRouter(prefix="/uploads", tags=["Uploads"])


def get_upload_service() -> UploadService:
    """Dependency для получения UploadService."""
    return UploadService()


# Требует роль APPLICANT для загрузки CV
require_applicant = RoleChecker([UserRole.APPLICANT])

# Требует роль EMPLOYER или CURATOR для загрузки медиа
require_employer_or_curator = RoleChecker([UserRole.EMPLOYER, UserRole.CURATOR])


@router.post(
    "/cv",
    response_model=CVUploadResponse,
    status_code=status.HTTP_200_OK,
    summary="Загрузка резюме (CV)",
    description="Загрузка файла резюме в формате PDF. Максимальный размер: 5MB. Доступно только соискателям.",
    dependencies=[Depends(require_applicant)],
)
async def upload_cv(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    upload_service: UploadService = Depends(get_upload_service),
) -> CVUploadResponse:
    """
    Загрузка резюме (CV) соискателя.

    Требования:
    - Формат: PDF
    - Максимальный размер: 5MB
    - Доступно только пользователям с ролью APPLICANT

    Возвращает публичный URL для использования в профиле.
    """
    result = await upload_service.upload_cv(
        file=file,
        user_role=current_user.role,
    )

    return CVUploadResponse(
        url=result["url"],
        filename=result["filename"],
        file_type=result["file_type"],
        file_size=result["file_size"],
    )


@router.post(
    "/media",
    response_model=MediaUploadResponse,
    status_code=status.HTTP_200_OK,
    summary="Загрузка медиа",
    description="Загрузка изображений (JPG, PNG, WEBP) или видео (MP4). Максимальный размер: 10MB.",
    dependencies=[Depends(require_employer_or_curator)],
)
async def upload_media(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    upload_service: UploadService = Depends(get_upload_service),
) -> MediaUploadResponse:
    """
    Загрузка медиафайлов (изображения или видео).

    Требования:
    - Форматы: JPG, PNG, WEBP (изображения), MP4 (видео)
    - Максимальный размер: 10MB
    - Доступно только пользователям с ролями EMPLOYER и CURATOR

    Возвращает публичный URL для использования в профиле компании или вакансии.
    """
    result = await upload_service.upload_media(
        file=file,
        user_role=current_user.role,
    )

    return MediaUploadResponse(
        url=result["url"],
        filename=result["filename"],
        file_type=result["file_type"],
        file_size=result["file_size"],
        media_type=result["media_type"],
    )
