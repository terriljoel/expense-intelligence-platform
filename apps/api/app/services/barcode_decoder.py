from io import BytesIO

from PIL import Image, UnidentifiedImageError

from app.services.receipt_capture import ALLOWED_IMAGE_TYPES
from app.services.text_normalization import normalize_barcode


class BarcodeImageValidationError(Exception):
    pass


def validate_barcode_image(
    content: bytes, media_type: str | None, max_bytes: int
) -> None:
    if not content or len(content) > max_bytes:
        raise BarcodeImageValidationError("Choose a barcode image within the upload limit")
    allowed = ALLOWED_IMAGE_TYPES.get((media_type or "").lower())
    if allowed is None or not allowed[1](content):
        raise BarcodeImageValidationError("Upload a valid JPEG, PNG, or WebP image")


def decode_barcode(content: bytes) -> tuple[str | None, str | None, str | None]:
    try:
        import zxingcpp

        with Image.open(BytesIO(content)) as image:
            results = zxingcpp.read_barcodes(image)
        for result in results:
            barcode = normalize_barcode(result.text)
            if barcode:
                return barcode, str(result.format).split(".")[-1], None
        return None, None, "No EAN/UPC barcode was detected. Try a closer, sharper photo."
    except (UnidentifiedImageError, OSError) as exc:
        raise BarcodeImageValidationError("The barcode image could not be read") from exc
    except Exception as exc:
        return None, None, f"Barcode decoder failed: {type(exc).__name__}"
