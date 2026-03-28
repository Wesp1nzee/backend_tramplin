"""
Схемы для загрузки файлов (CV и медиа).
"""

from pydantic import BaseModel, ConfigDict, Field


class SchemaBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UploadResponse(SchemaBase):
    """Ответ после успешной загрузки файла."""

    url: str = Field(..., description="Публичный URL загруженного файла")
    filename: str = Field(..., description="Имя файла")
    file_type: str = Field(..., description="MIME тип файла")
    file_size: int = Field(..., description="Размер файла в байтах")


class CVUploadResponse(UploadResponse):
    """Ответ после загрузки CV (резюме)."""

    pass


class MediaUploadResponse(UploadResponse):
    """Ответ после загрузки медиа (изображение/видео)."""

    media_type: str = Field(..., description="Тип медиа: image или video")
