"""
Сервис загрузки файлов (CV и медиа).

Отвечает за:
  - Валидацию MIME типов и размеров файлов
  - Генерацию безопасных имён файлов (UUID)
  - Сохранение через StorageBackend (S3)
  - Возврат публичных URL
"""

import io
import uuid
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from src.core.config import settings
from src.core.exceptions import PermissionDeniedError
from src.models.enums import UserRole
from src.services.storage import StorageBackend, get_storage_backend


class FileValidationError(PermissionDeniedError):
    """Исключение при ошибке валидации файла."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail=detail)


class UploadService:
    """
    Сервис загрузки файлов.

    Поддерживает:
      - Загрузку CV (PDF, макс. 5MB)
      - Загрузку медиа (изображения/видео, макс. 10MB)
    """

    # Допустимые MIME типы для CV
    CV_ALLOWED_MIME_TYPES = {"application/pdf"}

    # Допустимые MIME типы для медиа
    MEDIA_ALLOWED_MIME_TYPES = {
        "image/jpeg",
        "image/png",
        "image/webp",
        "video/mp4",
    }

    # Максимальные размеры (в байтах)
    MAX_CV_SIZE_BYTES: int
    MAX_MEDIA_SIZE_BYTES: int

    def __init__(
        self,
        storage_backend: StorageBackend | None = None,
        max_cv_size_mb: int | None = None,
        max_media_size_mb: int | None = None,
    ) -> None:
        """
        Инициализация сервиса загрузки.

        Args:
            storage_backend: Бэкенд хранилища (по умолчанию LocalStorage)
            max_cv_size_mb: Максимальный размер CV в MB
            max_media_size_mb: Максимальный размер медиа в MB
        """
        self.storage = storage_backend or get_storage_backend()
        self.max_cv_size_bytes = (max_cv_size_mb or settings.MAX_IMAGE_SIZE_MB) * 1024 * 1024
        self.max_media_size_bytes = (max_media_size_mb or 10) * 1024 * 1024

    def _generate_secure_filename(self, original_filename: str) -> str:
        """
        Генерирует безопасное имя файла используя UUID.

        Args:
            original_filename: Оригинальное имя файла

        Returns:
            str: Безопасное имя файла (uuid.extension)
        """
        # Получаем расширение из оригинального имени
        extension = Path(original_filename).suffix.lower()

        # Генерируем UUID для имени файла
        unique_id = uuid.uuid4().hex

        return f"{unique_id}{extension}"

    def _validate_file_size(self, file_size: int, max_size: int, file_type: str) -> None:
        """
        Проверить размер файла.

        Args:
            file_size: Размер файла в байтах
            max_size: Максимальный допустимый размер
            file_type: Тип файла для сообщения об ошибке

        Raises:
            FileValidationError: Если файл слишком большой
        """
        if file_size > max_size:
            max_mb = max_size // (1024 * 1024)
            raise FileValidationError(detail=f"File size exceeds maximum limit of {max_mb}MB for {file_type}")

    def _validate_mime_type(self, mime_type: str, allowed_types: set[str], file_type: str) -> None:
        """
        Проверить MIME тип файла.

        Args:
            mime_type: MIME тип файла
            allowed_types: Разрешённые MIME типы
            file_type: Тип файла для сообщения об ошибке

        Raises:
            FileValidationError: Если тип файла не разрешён
        """
        if mime_type not in allowed_types:
            raise FileValidationError(
                detail=f"File type '{mime_type}' is not allowed for {file_type}. Allowed types: {', '.join(allowed_types)}"
            )

    async def upload_cv(
        self,
        file: UploadFile,
        user_role: UserRole,
    ) -> dict[str, Any]:
        """
        Загрузить CV (резюме) пользователя.

        Args:
            file: Загруженный файл
            user_role: Роль пользователя (только APPLICANT)

        Returns:
            dict: Информация о загруженном файле (url, filename, etc.)

        Raises:
            FileValidationError: При ошибке валидации
            PermissionDeniedError: Если у пользователя нет прав
        """
        # Проверка прав доступа
        if user_role != UserRole.APPLICANT:
            raise PermissionDeniedError(detail="Only applicants can upload CVs")

        # Проверка размера
        file_content = await file.read()
        file_size = len(file_content)
        self._validate_file_size(file_size, self.max_cv_size_bytes, "CV")

        # Проверка MIME типа
        mime_type = file.content_type or ""
        self._validate_mime_type(mime_type, self.CV_ALLOWED_MIME_TYPES, "CV")

        # Генерируем безопасное имя файла
        secure_filename = self._generate_secure_filename(file.filename or "cv.pdf")

        # Сохраняем файл через S3 storage
        file_io = io.BytesIO(file_content)
        public_url = await self.storage.save_file(
            file=file_io,
            filename=secure_filename,
            folder="cvs",
            content_type=mime_type,
        )

        return {
            "url": public_url,
            "filename": secure_filename,
            "file_type": mime_type,
            "file_size": file_size,
        }

    async def upload_media(
        self,
        file: UploadFile,
        user_role: UserRole,
    ) -> dict[str, Any]:
        """
        Загрузить медиафайл (изображение или видео).

        Args:
            file: Загруженный файл
            user_role: Роль пользователя (только EMPLOYER, CURATOR)

        Returns:
            dict: Информация о загруженном файле

        Raises:
            FileValidationError: При ошибке валидации
            PermissionDeniedError: Если у пользователя нет прав
        """
        # Проверка прав доступа
        if user_role not in (UserRole.EMPLOYER, UserRole.CURATOR):
            raise PermissionDeniedError(detail="Only employers and curators can upload media")

        # Проверка размера
        file_content = await file.read()
        file_size = len(file_content)
        self._validate_file_size(file_size, self.max_media_size_bytes, "media")

        # Проверка MIME типа
        mime_type = file.content_type or ""
        self._validate_mime_type(mime_type, self.MEDIA_ALLOWED_MIME_TYPES, "media")

        # Определяем тип медиа
        media_type = "image" if mime_type.startswith("image/") else "video"

        # Генерируем безопасное имя файла
        secure_filename = self._generate_secure_filename(file.filename or "media")

        # Определяем папку в зависимости от типа
        folder = "media/images" if media_type == "image" else "media/videos"

        # Сохраняем файл через S3 storage
        file_io = io.BytesIO(file_content)
        public_url = await self.storage.save_file(
            file=file_io,
            filename=secure_filename,
            folder=folder,
            content_type=mime_type,
        )

        return {
            "url": public_url,
            "filename": secure_filename,
            "file_type": mime_type,
            "file_size": file_size,
            "media_type": media_type,
        }
