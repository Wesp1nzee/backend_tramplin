"""
Сервис для работы с файловым хранилищем (S3/MinIO).

Поддерживает различные бэкенды хранения через интерфейс StorageBackend.
Текущая реализация: S3Storage (MinIO/S3 совместимое хранилище).
"""

import re
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, BinaryIO

from aiobotocore.session import get_session
from botocore.config import Config
from botocore.response import StreamingBody
from fastapi import UploadFile

from src.core.config import settings

# Минимальный размер части S3 multipart — 5 МБ (требование AWS).
_MULTIPART_CHUNK_SIZE = 5 * 1024 * 1024  # 5 МБ


class StorageError(Exception):
    """Исключение при ошибке хранилища."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(self.detail)


class StorageBackend(ABC):
    """
    Абстрактный базовый класс для хранилищ.

    Позволяет легко переключаться между LocalStorage, S3, MinIO.
    """

    @abstractmethod
    async def save_file(
        self,
        file: BinaryIO,
        filename: str,
        folder: str = "",
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Сохранить файл в хранилище.

        Args:
            file: Файловый объект (BinaryIO)
            filename: Имя файла
            folder: Папка внутри хранилища
            content_type: MIME тип файла

        Returns:
            str: Публичный URL файла
        """
        pass

    @abstractmethod
    async def delete_file(self, file_path: str) -> None:
        """
        Удалить файл из хранилища.

        Args:
            file_path: Путь к файлу
        """
        pass

    @abstractmethod
    async def file_exists(self, file_path: str) -> bool:
        """
        Проверить существование файла.

        Args:
            file_path: Путь к файлу

        Returns:
            bool: True если файл существует
        """
        pass

    @abstractmethod
    async def get_public_url(self, file_path: str) -> str:
        """
        Получить публичный URL файла.

        Args:
            file_path: Путь к файлу

        Returns:
            str: Публичный URL
        """
        pass


class S3Storage(StorageBackend):
    """
    S3/MinIO хранилище.

    Поддерживает:
      - Multipart upload для больших файлов
      - Presigned URLs для безопасного доступа
      - Потоковая загрузка
    """

    def __init__(self) -> None:
        self.session = get_session()
        self.config = {
            "aws_access_key_id": settings.S3_ACCESS_KEY,
            "aws_secret_access_key": settings.S3_SECRET_KEY,
            "endpoint_url": settings.S3_ENDPOINT_URL,
            "region_name": settings.S3_REGION,
        }
        self.s3_config = Config(s3={"addressing_style": "path"})
        self._bucket_initialized = False

    @asynccontextmanager
    async def get_client(self) -> AsyncIterator[Any]:
        """Получить клиент S3."""
        async with self.session.create_client("s3", config=self.s3_config, **self.config) as client:
            yield client

    async def init_bucket(self) -> None:
        """Создает корзину, если она не существует."""
        if self._bucket_initialized:
            return

        async with self.get_client() as client:
            try:
                await client.head_bucket(Bucket=settings.S3_BUCKET_NAME)
            except Exception:
                await client.create_bucket(Bucket=settings.S3_BUCKET_NAME)

        self._bucket_initialized = True

    async def save_file(
        self,
        file: BinaryIO,
        filename: str,
        folder: str = "",
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Сохранить файл в S3.

        Args:
            file: Файловый объект (BinaryIO)
            filename: Имя файла
            folder: Папка в bucket
            content_type: MIME тип

        Returns:
            str: Публичный URL файла
        """
        await self.init_bucket()

        # Формируем объект key
        object_key = f"{folder}/{filename}" if folder else filename

        # Читаем данные из BinaryIO
        file_data = file.read()

        async with self.get_client() as client:
            await client.put_object(
                Bucket=settings.S3_BUCKET_NAME,
                Key=object_key,
                Body=file_data,
                ContentType=content_type,
            )

        # Возвращаем публичный URL
        return await self.get_public_url(object_key)

    async def upload_file_multipart(
        self,
        upload: UploadFile,
        object_key: str,
        content_type: str,
    ) -> int:
        """
        Потоковая загрузка файла в S3 через Multipart Upload.

        Читает файл чанками по _MULTIPART_CHUNK_SIZE (5 МБ).
        В памяти одновременно живёт ровно один чанк.

        Args:
            upload: UploadFile из FastAPI
            object_key: Ключ объекта в S3
            content_type: MIME тип

        Returns:
            int: Общий размер загруженных байт
        """
        await self.init_bucket()

        async with self.get_client() as client:
            mpu = await client.create_multipart_upload(
                Bucket=settings.S3_BUCKET_NAME,
                Key=object_key,
                ContentType=content_type,
            )
            upload_id: str = mpu["UploadId"]
            parts: list[dict[str, int | Any]] = []
            part_number = 1
            total_bytes = 0

            try:
                while True:
                    chunk = await upload.read(_MULTIPART_CHUNK_SIZE)
                    if not chunk:
                        break

                    resp = await client.upload_part(
                        Bucket=settings.S3_BUCKET_NAME,
                        Key=object_key,
                        UploadId=upload_id,
                        PartNumber=part_number,
                        Body=chunk,
                    )
                    parts.append({"PartNumber": part_number, "ETag": resp["ETag"]})
                    total_bytes += len(chunk)
                    part_number += 1

                # Пустые файлы тоже нужно загрузить
                if not parts:
                    resp = await client.upload_part(
                        Bucket=settings.S3_BUCKET_NAME,
                        Key=object_key,
                        UploadId=upload_id,
                        PartNumber=1,
                        Body=b"",
                    )
                    parts.append({"PartNumber": 1, "ETag": resp["ETag"]})

                await client.complete_multipart_upload(
                    Bucket=settings.S3_BUCKET_NAME,
                    Key=object_key,
                    UploadId=upload_id,
                    MultipartUpload={"Parts": parts},
                )

            except Exception:
                try:
                    await client.abort_multipart_upload(
                        Bucket=settings.S3_BUCKET_NAME,
                        Key=object_key,
                        UploadId=upload_id,
                    )
                except Exception:  # nosec B105,B110
                    pass
                raise

        return total_bytes

    async def delete_file(self, file_path: str) -> None:
        """
        Удалить файл из S3.

        Args:
            file_path: Ключ объекта (например, cvs/uuid.pdf)
        """
        # Если передан полный URL, извлекаем ключ
        if file_path.startswith(settings.S3_ENDPOINT_URL):
            # Извлекаем ключ из URL вида: http://s3:9000/bucket/cvs/uuid.pdf
            parts = file_path.replace(settings.S3_ENDPOINT_URL, "").lstrip("/").split("/", 1)
            if len(parts) > 1:
                file_path = parts[1]

        async with self.get_client() as client:
            await client.delete_object(Bucket=settings.S3_BUCKET_NAME, Key=file_path)

    async def file_exists(self, file_path: str) -> bool:
        """
        Проверить существование файла.

        Args:
            file_path: Ключ объекта

        Returns:
            bool: True если файл существует
        """
        # Если передан полный URL, извлекаем ключ
        if file_path.startswith(settings.S3_ENDPOINT_URL):
            parts = file_path.replace(settings.S3_ENDPOINT_URL, "").lstrip("/").split("/", 1)
            if len(parts) > 1:
                file_path = parts[1]

        async with self.get_client() as client:
            try:
                await client.head_object(Bucket=settings.S3_BUCKET_NAME, Key=file_path)
                return True
            except Exception:
                return False

    async def get_public_url(self, file_path: str) -> str:
        """
        Получить публичный URL файла.

        Если S3 настроен на публичный доступ — возвращает прямой URL.
        Иначе возвращает presigned URL.

        Args:
            file_path: Ключ объекта

        Returns:
            str: Публичный URL
        """
        # Если endpoint публичный (не localhost), используем прямой URL
        if "localhost" not in settings.S3_ENDPOINT_URL and "127.0.0.1" not in settings.S3_ENDPOINT_URL:
            return f"{settings.S3_ENDPOINT_URL}/{settings.S3_BUCKET_NAME}/{file_path}"

        # Иначе используем presigned URL
        return await self.get_presigned_url(file_path)

    async def get_presigned_url(
        self,
        object_key: str,
        original_filename: str | None = None,
        expires_in: int = 3600,
        download: bool = False,
    ) -> str:
        """
        Получить presigned URL для доступа к файлу.

        Args:
            object_key: Ключ объекта
            original_filename: Оригинальное имя файла для Content-Disposition
            expires_in: Время действия в секундах
            download: Если True, файл будет скачан, иначе открыт в браузере

        Returns:
            str: Presigned URL
        """
        params = {"Bucket": settings.S3_BUCKET_NAME, "Key": object_key}

        if original_filename:
            safe_filename = re.sub(r"[^\w\-. ]", "_", original_filename)
            disposition_type = "attachment" if download else "inline"
            content_disposition = f'{disposition_type}; filename="{safe_filename}"'
            params["ResponseContentDisposition"] = content_disposition

            import mimetypes

            content_type, _ = mimetypes.guess_type(original_filename)
            if content_type:
                params["ResponseContentType"] = content_type

        async with self.get_client() as client:
            url: str = await client.generate_presigned_url(
                "get_object",
                Params=params,
                ExpiresIn=expires_in,
            )
            return url

    async def get_file_content(self, object_key: str) -> bytes:
        """
        Получить содержимое файла из S3.

        Args:
            object_key: Ключ объекта

        Returns:
            bytes: Содержимое файла
        """
        async with self.get_client() as client:
            response = await client.get_object(Bucket=settings.S3_BUCKET_NAME, Key=object_key)
            body = response["Body"]
            content: bytes = await body.read()
            return content

    async def get_file_stream(self, object_key: str) -> StreamingBody:
        """
        Получить стрим файла из S3.

        Args:
            object_key: Ключ объекта

        Returns:
            StreamingBody: Поток данных
        """
        async with self.get_client() as client:
            response = await client.get_object(Bucket=settings.S3_BUCKET_NAME, Key=object_key)
            return response["Body"]


# Глобальный экземпляр хранилища
_storage_backend: StorageBackend | None = None


def get_storage_backend() -> StorageBackend:
    """
    Получить экземпляр хранилища.

    Использует S3Storage по умолчанию.
    """
    global _storage_backend

    if _storage_backend is None:
        _storage_backend = S3Storage()

    return _storage_backend
