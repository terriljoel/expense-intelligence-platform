from pathlib import Path

from app.core.config import get_settings
from app.integrations.azure.blob_storage import (
    AzureBlobReceiptImageStorage,
)
from app.services.receipt_image_storage import (
    LocalReceiptImageStorage,
    build_receipt_image_storage,
)


IMAGE = b"receipt-image"


class FakeDownload:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def readall(self) -> bytes:
        return self.content


class FakeContainer:
    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}

    def upload_blob(
        self,
        *,
        name: str,
        data: bytes,
        overwrite: bool,
        **options: object,
    ) -> None:
        assert overwrite is False
        assert options == {}
        self.blobs[name] = data

    def download_blob(self, name: str) -> FakeDownload:
        return FakeDownload(self.blobs[name])

    def delete_blob(self, name: str) -> None:
        del self.blobs[name]


def test_local_storage_round_trip(tmp_path: Path) -> None:
    storage = LocalReceiptImageStorage(tmp_path)
    storage.put("household/capture.jpg", IMAGE, "image/jpeg")

    assert storage.get("household/capture.jpg") == IMAGE
    storage.delete("household/capture.jpg")
    assert not (tmp_path / "household" / "capture.jpg").exists()


def test_azure_blob_storage_round_trip_without_sdk_calls() -> None:
    container = FakeContainer()
    storage = AzureBlobReceiptImageStorage(
        get_settings().model_copy(), container_client=container
    )
    storage.put("household/capture.jpg", IMAGE, "image/jpeg")

    assert storage.get("household/capture.jpg") == IMAGE
    storage.delete("household/capture.jpg")
    assert container.blobs == {}


def test_storage_provider_can_switch_to_local(tmp_path: Path) -> None:
    settings = get_settings().model_copy(
        update={
            "receipt_storage_provider": "local",
            "receipt_image_dir": tmp_path,
        }
    )

    assert isinstance(build_receipt_image_storage(settings), LocalReceiptImageStorage)
