"""Private Azure Blob Storage adapter for receipt images."""

from typing import Any

from app.core.config import Settings
from app.services.receipt_image_storage import (
    ReceiptImageNotFoundError,
    ReceiptImageStorageError,
)


class AzureBlobReceiptImageStorage:
    """Store receipt images in one private Azure Blob container."""

    def __init__(
        self,
        settings: Settings,
        container_client: Any | None = None,
    ) -> None:
        self.container_name = settings.azure_storage_container
        self._content_settings_type: Any | None = None
        if container_client is not None:
            self.container = container_client
            return

        try:
            from azure.storage.blob import BlobServiceClient, ContentSettings
        except ImportError as exc:
            raise ReceiptImageStorageError(
                "Install the azure-storage-blob dependency"
            ) from exc
        self._content_settings_type = ContentSettings

        try:
            if settings.azure_storage_connection_string:
                service = BlobServiceClient.from_connection_string(
                    settings.azure_storage_connection_string
                )
            elif settings.azure_storage_account_url:
                from azure.identity import DefaultAzureCredential

                service = BlobServiceClient(
                    account_url=settings.azure_storage_account_url,
                    credential=DefaultAzureCredential(),
                )
            else:
                raise ReceiptImageStorageError(
                    "Azure Blob storage needs a connection string or account URL"
                )
            self.container = service.get_container_client(self.container_name)
        except ReceiptImageStorageError:
            raise
        except Exception as exc:
            raise ReceiptImageStorageError(
                "Could not configure Azure Blob Storage"
            ) from exc

    def put(self, object_key: str, content: bytes, media_type: str) -> None:
        options: dict[str, Any] = {}
        if self._content_settings_type is not None:
            options["content_settings"] = self._content_settings_type(
                content_type=media_type
            )
        try:
            self.container.upload_blob(
                name=object_key,
                data=content,
                overwrite=False,
                **options,
            )
        except Exception as exc:
            raise ReceiptImageStorageError(
                "Could not upload the receipt image to Azure Blob Storage"
            ) from exc

    def get(self, object_key: str) -> bytes:
        try:
            return self.container.download_blob(object_key).readall()
        except Exception as exc:
            if type(exc).__name__ == "ResourceNotFoundError":
                raise ReceiptImageNotFoundError(
                    "Receipt image was not found in Azure Blob Storage"
                ) from exc
            raise ReceiptImageStorageError(
                "Could not download the receipt image from Azure Blob Storage"
            ) from exc

    def delete(self, object_key: str) -> None:
        try:
            self.container.delete_blob(object_key)
        except Exception as exc:
            if type(exc).__name__ == "ResourceNotFoundError":
                raise ReceiptImageNotFoundError(
                    "Receipt image was not found in Azure Blob Storage"
                ) from exc
            raise ReceiptImageStorageError(
                "Could not delete the receipt image from Azure Blob Storage"
            ) from exc
