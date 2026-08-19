from __future__ import annotations

import hashlib
from dataclasses import replace
import re
import subprocess
import tempfile
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import Merchant, PaymentMethod, ReceiptCapture
from app.services.duplicate_receipt import find_duplicate_receipt
from app.services.merchant import normalize_merchant_address, normalize_merchant_name
from app.services.ocr import (
    OcrProcessingError,
    OcrProvider,
    OcrResult,
    ReceiptSuggestions,
)
from app.services.receipt_image_storage import (
    ReceiptImageStorage,
    ReceiptImageStorageError,
)
from app.services.diagnostics import record_error


ALLOWED_IMAGE_TYPES = {
    "image/jpeg": (".jpg", lambda data: data.startswith(b"\xff\xd8\xff")),
    "image/png": (
        ".png",
        lambda data: data.startswith(b"\x89PNG\r\n\x1a\n"),
    ),
    "image/webp": (
        ".webp",
        lambda data: len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP",
    ),
}


class CaptureNotFoundError(Exception):
    """Raised when a capture is missing or outside the active household."""


class CaptureValidationError(Exception):
    """Raised when an uploaded file is empty, too large, or not an image."""


class DuplicateCaptureError(Exception):
    """Raised when the same image was already captured in the household."""


class CaptureAlreadyUsedError(Exception):
    """Raised when a capture is already linked to a receipt."""


class TesseractOcrProvider:
    """Run the local Tesseract executable without a shell."""

    def __init__(self, settings: Settings) -> None:
        self.command = settings.tesseract_command
        self.language = settings.tesseract_language
        self.timeout_seconds = settings.tesseract_timeout_seconds

    def extract_text(self, image: bytes) -> OcrResult:
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".img") as temporary:
                temporary.write(image)
                temporary_path = Path(temporary.name)
            completed = subprocess.run(
                [
                    self.command,
                    str(temporary_path),
                    "stdout",
                    "-l",
                    self.language,
                    "--psm",
                    "6",
                ],
                capture_output=True,
                check=False,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise OcrProcessingError(
                "Tesseract is not installed or TESSERACT_COMMAND is invalid"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise OcrProcessingError("Tesseract OCR timed out") from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

        raw_text = completed.stdout.strip()
        if completed.returncode != 0:
            detail = completed.stderr.strip().splitlines()
            message = detail[-1] if detail else "Tesseract OCR failed"
            raise OcrProcessingError(message[:500])
        if not raw_text:
            raise OcrProcessingError("OCR completed but found no text")
        return OcrResult(provider="tesseract", raw_text=raw_text)


def get_ocr_provider() -> OcrProvider:
    settings = get_settings()
    provider = settings.ocr_provider.strip().lower()
    if provider == "azure":
        from app.integrations.azure.document_intelligence import (
            AzureReceiptOcrProvider,
        )

        return AzureReceiptOcrProvider(settings)
    if provider == "tesseract":
        return TesseractOcrProvider(settings)
    raise OcrProcessingError("OCR_PROVIDER must be either 'azure' or 'tesseract'")


def _parse_date(text: str) -> date | None:
    patterns = (
        (r"(?<!\d)(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)", "ymd"),
        (r"(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](20\d{2})(?!\d)", "dmy"),
        (r"(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](\d{2})(?!\d)", "dmy2"),
    )
    for pattern, order in patterns:
        match = re.search(pattern, text)
        if match is None:
            continue
        values = [int(part) for part in match.groups()]
        if order == "ymd":
            year, month, day = values
        else:
            day, month, year = values
            if order == "dmy2":
                year += 2000
        try:
            return date(year, month, day)
        except ValueError:
            continue
    return None


def _parse_money(value: str) -> Decimal | None:
    compact = value.replace(" ", "")
    if "," in compact and "." in compact:
        if compact.rfind(",") > compact.rfind("."):
            compact = compact.replace(".", "").replace(",", ".")
        else:
            compact = compact.replace(",", "")
    else:
        compact = compact.replace(",", ".")
    try:
        amount = Decimal(compact).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None
    return amount if amount >= 0 else None


def extract_receipt_suggestions(raw_text: str) -> ReceiptSuggestions:
    lines = [" ".join(line.split()) for line in raw_text.splitlines()]
    lines = [line for line in lines if line]
    merchant = next(
        (
            line[:200]
            for line in lines[:5]
            if re.search(r"[A-Za-zÄÖÜäöüß]", line)
            and not re.search(r"\b(?:tel|www\.|straße|str\.|ust-id)\b", line, re.I)
        ),
        None,
    )
    purchase_date = _parse_date(raw_text)
    currency = "EUR" if re.search(r"€|\bEUR\b", raw_text, re.I) else None

    amount_pattern = re.compile(
        r"(?<![\d.,])(?:\d{1,3}(?:[. ]\d{3})+|\d{1,7})[.,]\d{2}(?!\d)"
    )
    total_keywords = re.compile(
        r"\b(?:gesamt|summe|total|betrag|zu\s+zahlen|amount)\b", re.I
    )
    candidates: list[Decimal] = []
    for line in reversed(lines):
        if not total_keywords.search(line):
            continue
        for match in amount_pattern.findall(line):
            amount = _parse_money(match)
            if amount is not None:
                candidates.append(amount)
        if candidates:
            break
    total = candidates[-1] if candidates else None
    payment = detect_payment_details(raw_text)
    return ReceiptSuggestions(
        merchant,
        purchase_date,
        currency,
        total,
        payment_type=payment[0],
        payment_provider=payment[1],
        payment_last_four=payment[2],
        receipt_number=detect_receipt_number(raw_text),
    )


def detect_payment_details(raw_text: str) -> tuple[str | None, str | None, str | None]:
    """Extract conservative payment hints from receipt text."""
    lowered = raw_text.casefold()
    provider = next(
        (
            name
            for token, name in (
                ("mastercard", "Mastercard"),
                ("master card", "Mastercard"),
                ("visa", "Visa"),
                ("paypal", "PayPal"),
                ("american express", "American Express"),
                ("amex", "American Express"),
            )
            if token in lowered
        ),
        None,
    )
    if re.search(r"\b(?:bar|cash|bargeld)\b", lowered):
        method_type = "cash"
    elif re.search(r"\b(?:paypal|apple pay|google pay)\b", lowered):
        method_type = "mobile_wallet"
    elif re.search(r"\b(?:kreditkarte|credit card)\b", lowered):
        method_type = "credit_card"
    elif re.search(r"\b(?:debit|ec[- ]?karte|girocard|karte)\b", lowered):
        method_type = "debit_card"
    else:
        method_type = None
    last_four_match = re.search(
        r"(?:\*{2,}|x{2,}|karte|card|pan)[^\d]{0,12}(\d{4})(?!\d)",
        lowered,
    )
    return method_type, provider, last_four_match.group(1) if last_four_match else None


def detect_receipt_number(raw_text: str) -> str | None:
    patterns = (
        r"\b(?:bon|beleg|kassenbon)[-\s]*(?:nr|nummer)\.?\s*[:#-]?\s*([A-Z0-9][A-Z0-9./-]{2,40})",
        r"\b(?:receipt)[-\s]*(?:no|number|#)\.?\s*[:#-]?\s*([A-Z0-9][A-Z0-9./-]{2,40})",
        r"\b(?:transaction|transaktion)[-\s]*(?:id|nr|nummer)\.?\s*[:#-]?\s*([A-Z0-9][A-Z0-9./-]{2,40})",
    )
    for pattern in patterns:
        match = re.search(pattern, raw_text, re.IGNORECASE)
        if match:
            return match.group(1).rstrip(".-/")[:100]
    return None


def detect_merchant_address(raw_text: str) -> str | None:
    """Find a conservative German street + postal-code/city pair."""
    lines = [" ".join(line.split()) for line in raw_text.splitlines()]
    lines = [line for line in lines if line][:20]
    postal_pattern = re.compile(r"^\d{5}\s+[^\W\d_][\w .'-]{1,80}$", re.UNICODE)
    street_pattern = re.compile(
        r"^[^\W\d_][\w .'-]{1,80}\s\d{1,5}[a-zA-Z]?$",
        re.IGNORECASE | re.UNICODE,
    )
    for index, line in enumerate(lines):
        if not postal_pattern.match(line) or index == 0:
            continue
        street = lines[index - 1]
        if street_pattern.match(street):
            return f"{street}, {line}"[:500]
    return None


def _match_payment_method(
    session: Session,
    *,
    household_id: UUID,
    user_id: UUID,
    payment_type: str | None,
    provider: str | None,
    last_four: str | None,
) -> tuple[UUID | None, str | None]:
    methods = list(
        session.scalars(
            select(PaymentMethod).where(
                PaymentMethod.household_id == household_id,
                PaymentMethod.user_id == user_id,
                PaymentMethod.is_active.is_(True),
            )
        )
    )
    if last_four:
        matches = [method for method in methods if method.last_four == last_four]
        if len(matches) == 1:
            return matches[0].id, f"Card ending {last_four} matched"
        if len(matches) > 1:
            return None, f"More than one active method ends in {last_four}"
    candidates = methods
    evidence: list[str] = []
    if provider:
        candidates = [
            method
            for method in candidates
            if provider.casefold() in (method.provider or method.name).casefold()
        ]
        evidence.append(provider)
    if payment_type:
        candidates = [
            method for method in candidates if method.method_type == payment_type
        ]
        evidence.append(payment_type.replace("_", " "))
    if evidence and len(candidates) == 1:
        return candidates[0].id, f"OCR detected {' / '.join(evidence)}"
    if evidence and len(candidates) > 1:
        return None, f"OCR detected {' / '.join(evidence)}, but multiple methods match"
    return None, "OCR did not provide enough payment details"


def _safe_original_filename(filename: str | None) -> str | None:
    if not filename:
        return None
    cleaned = Path(filename).name.replace("\x00", "").strip()
    return cleaned[:255] or None


def _readable_size(byte_count: int) -> str:
    if byte_count < 1024 * 1024:
        return f"{byte_count / 1024:g} KB"
    return f"{byte_count / (1024 * 1024):g} MB"


def create_capture(
    session: Session,
    *,
    settings: Settings,
    storage: ReceiptImageStorage,
    household_id: UUID,
    uploaded_by_user_id: UUID,
    filename: str | None,
    media_type: str | None,
    content: bytes,
) -> ReceiptCapture:
    if not content:
        raise CaptureValidationError("Choose a non-empty receipt image")
    if len(content) > settings.receipt_image_max_bytes:
        raise CaptureValidationError(
            f"Receipt image exceeds the {_readable_size(settings.receipt_image_max_bytes)} upload limit. "
            "Choose a smaller image or reduce its resolution."
        )
    image_type = (media_type or "").lower()
    allowed = ALLOWED_IMAGE_TYPES.get(image_type)
    if allowed is None or not allowed[1](content):
        raise CaptureValidationError("Upload a valid JPEG, PNG, or WebP receipt image")

    image_sha256 = hashlib.sha256(content).hexdigest()
    duplicate = session.scalar(
        select(ReceiptCapture.id).where(
            ReceiptCapture.household_id == household_id,
            ReceiptCapture.image_sha256 == image_sha256,
        )
    )
    if duplicate is not None:
        raise DuplicateCaptureError

    capture_id = uuid4()
    extension = allowed[0]
    object_key = f"{household_id}/{capture_id}{extension}"
    storage.put(object_key, content, image_type)

    capture = ReceiptCapture(
        id=capture_id,
        household_id=household_id,
        uploaded_by_user_id=uploaded_by_user_id,
        original_filename=_safe_original_filename(filename),
        media_type=image_type,
        byte_size=len(content),
        image_sha256=image_sha256,
        image_object_key=object_key,
        ocr_status="pending",
    )
    session.add(capture)
    try:
        session.flush()
    except IntegrityError as exc:
        storage.delete(object_key)
        raise DuplicateCaptureError from exc
    return capture


def get_capture(
    session: Session,
    *,
    household_id: UUID,
    capture_id: UUID,
    for_update: bool = False,
) -> ReceiptCapture:
    statement = select(ReceiptCapture).where(
        ReceiptCapture.id == capture_id,
        ReceiptCapture.household_id == household_id,
    )
    if for_update:
        statement = statement.with_for_update()
    capture = session.scalar(statement)
    if capture is None:
        raise CaptureNotFoundError
    return capture


def capture_image_bytes(capture: ReceiptCapture, storage: ReceiptImageStorage) -> bytes:
    return storage.get(capture.image_object_key)


def process_capture_ocr(
    session: Session,
    *,
    storage: ReceiptImageStorage,
    provider: OcrProvider,
    household_id: UUID,
    capture_id: UUID,
) -> ReceiptCapture:
    capture = get_capture(
        session,
        household_id=household_id,
        capture_id=capture_id,
        for_update=True,
    )
    if capture.receipt_id is not None:
        raise CaptureAlreadyUsedError
    capture.ocr_status = "processing"
    capture.ocr_error = None
    session.flush()

    try:
        result = provider.extract_text(capture_image_bytes(capture, storage))
        suggestions = result.suggestions or extract_receipt_suggestions(result.raw_text)
        detected_type, detected_provider, detected_last_four = detect_payment_details(
            result.raw_text
        )
        suggestions = replace(
            suggestions,
            merchant_address=suggestions.merchant_address
            or detect_merchant_address(result.raw_text),
            payment_type=suggestions.payment_type or detected_type,
            payment_provider=suggestions.payment_provider or detected_provider,
            payment_last_four=suggestions.payment_last_four or detected_last_four,
            receipt_number=suggestions.receipt_number
            or detect_receipt_number(result.raw_text),
        )
    except (OcrProcessingError, ReceiptImageStorageError) as exc:
        record_error(
            message=str(exc),
            method="OCR",
            path=f"/receipt-captures/{capture_id}/ocr",
            status_code=422,
            exception=exc,
            level="warning",
        )
        capture.ocr_status = "failed"
        capture.ocr_error = str(exc)[:500]
        capture.ocr_completed_at = datetime.now(timezone.utc)
        session.flush()
        return capture

    capture.ocr_status = "succeeded"
    capture.ocr_provider = result.provider
    capture.ocr_raw_text = result.raw_text
    capture.ocr_result = result.provider_payload
    capture.suggested_items = [
        {
            "description": item.description,
            "quantity": str(item.quantity) if item.quantity is not None else None,
            "unit_price": (
                str(item.unit_price) if item.unit_price is not None else None
            ),
            "line_total": str(item.line_total),
        }
        for item in result.line_items
    ]
    capture.ocr_error = None
    capture.suggested_merchant_name = suggestions.merchant_name
    capture.suggested_merchant_address = suggestions.merchant_address
    capture.suggested_merchant_phone = suggestions.merchant_phone
    capture.suggested_purchase_date = suggestions.purchase_date
    capture.suggested_transaction_time = suggestions.transaction_time
    capture.suggested_currency = suggestions.currency
    capture.suggested_total = suggestions.total
    capture.suggested_subtotal = suggestions.subtotal
    capture.suggested_tax = suggestions.tax
    capture.suggested_tip = suggestions.tip
    capture.suggested_payment_type = suggestions.payment_type
    capture.suggested_payment_provider = suggestions.payment_provider
    capture.suggested_payment_last_four = suggestions.payment_last_four
    capture.suggested_payment_method_id, capture.suggested_payment_reason = (
        _match_payment_method(
            session,
            household_id=household_id,
            user_id=capture.uploaded_by_user_id,
            payment_type=suggestions.payment_type,
            provider=suggestions.payment_provider,
            last_four=suggestions.payment_last_four,
        )
    )
    capture.suggested_receipt_number = suggestions.receipt_number
    capture.possible_duplicate_receipt_id = None
    capture.duplicate_match_level = None
    capture.duplicate_reason = None
    if suggestions.merchant_name and suggestions.purchase_date:
        merchant = session.scalar(
            select(Merchant).where(
                Merchant.household_id == household_id,
                Merchant.normalized_name
                == normalize_merchant_name(suggestions.merchant_name),
                Merchant.normalized_address
                == normalize_merchant_address(suggestions.merchant_address),
            )
        )
        if merchant is not None:
            duplicate = find_duplicate_receipt(
                session,
                household_id=household_id,
                merchant_id=merchant.id,
                purchase_date=suggestions.purchase_date,
                transaction_time=suggestions.transaction_time,
                total=suggestions.total,
                currency=suggestions.currency,
                receipt_number=suggestions.receipt_number,
            )
            if duplicate is not None:
                capture.possible_duplicate_receipt_id = duplicate.receipt_id
                capture.duplicate_match_level = duplicate.level
                capture.duplicate_reason = duplicate.reason
    capture.ocr_completed_at = datetime.now(timezone.utc)
    session.flush()
    return capture


def delete_capture(
    session: Session,
    *,
    storage: ReceiptImageStorage,
    household_id: UUID,
    capture_id: UUID,
) -> None:
    capture = get_capture(
        session,
        household_id=household_id,
        capture_id=capture_id,
        for_update=True,
    )
    if capture.receipt_id is not None:
        raise CaptureAlreadyUsedError
    session.delete(capture)
    session.flush()
    storage.delete(capture.image_object_key)
