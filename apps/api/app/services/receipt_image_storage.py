"""Provider-neutral storage contracts for private receipt images."""

from pathlib import Path
from typing import Protocol

from app.core.config import Settings


class ReceiptImageStorageError(Exception):
    """Raised when a receipt image storage operation fails."""


class ReceiptImageNotFoundError(ReceiptImageStorageError):
    """Raised when an expected receipt image does not exist."""


class ReceiptImageStorage(Protocol):
    def put(self, object_key: str, content: bytes, media_type: str) -> None: ...

    def get(self, object_key: str) -> bytes: ...

    def delete(self, object_key: str) -> None: ...


class LocalReceiptImageStorage:
    """Store private receipt images below a configured local directory."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path(self, object_key: str) -> Path:
        path = (self.root / object_key).resolve()
        if self.root not in path.parents:
            raise ReceiptImageStorageError("Invalid receipt image object key")
        return path

    def put(self, object_key: str, content: bytes, media_type: str) -> None:
        del media_type
        destination = self._path(object_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(f"{destination.suffix}.tmp")
        try:
            temporary.write_bytes(content)
            temporary.replace(destination)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise ReceiptImageStorageError(
                "Could not store the receipt image locally"
            ) from exc

    def get(self, object_key: str) -> bytes:
        try:
            return self._path(object_key).read_bytes()
        except FileNotFoundError as exc:
            raise ReceiptImageNotFoundError("Receipt image was not found") from exc
        except OSError as exc:
            raise ReceiptImageStorageError(
                "Could not read the local receipt image"
            ) from exc

    def delete(self, object_key: str) -> None:
        try:
            self._path(object_key).unlink()
        except FileNotFoundError as exc:
            raise ReceiptImageNotFoundError("Receipt image was not found") from exc
        except OSError as exc:
            raise ReceiptImageStorageError(
                "Could not delete the local receipt image"
            ) from exc


def build_receipt_image_storage(settings: Settings) -> ReceiptImageStorage:
    provider = settings.receipt_storage_provider.strip().lower()
    if provider == "local":
        return LocalReceiptImageStorage(settings.receipt_image_dir)
    if provider == "azure_blob":
        from app.integrations.azure.blob_storage import (
            AzureBlobReceiptImageStorage,
        )

        return AzureBlobReceiptImageStorage(settings)
    raise ReceiptImageStorageError(
        "RECEIPT_STORAGE_PROVIDER must be 'local' or 'azure_blob'"
    )
