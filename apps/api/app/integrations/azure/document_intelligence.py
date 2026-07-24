"""Azure Document Intelligence adapter for the prebuilt receipt model."""

from io import BytesIO
from datetime import date, time
from decimal import Decimal, InvalidOperation
import json
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import Settings
from app.services.ocr import (
    OcrProcessingError,
    OcrLineItem,
    OcrResult,
    ReceiptSuggestions,
)


class AzureReceiptOcrProvider:
    """Translate Azure SDK results into provider-neutral OCR results."""

    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self.endpoint = settings.azure_document_intelligence_endpoint
        self.key = settings.azure_document_intelligence_key
        self.locale = settings.azure_document_intelligence_locale
        self.timeout_seconds = settings.azure_document_intelligence_timeout_seconds
        self.max_document_bytes = settings.azure_document_intelligence_max_bytes
        if client is not None:
            self.client = client
            return
        if not self.endpoint or not self.key:
            self.client = None
            return

        # Keeping SDK imports here means the rest of the application has no
        # dependency on Azure types.
        try:
            from azure.ai.documentintelligence import (
                DocumentIntelligenceClient,
            )
            from azure.core.credentials import AzureKeyCredential
        except ImportError as exc:
            raise OcrProcessingError(
                "Install the azure-ai-documentintelligence dependency"
            ) from exc
        self.client = DocumentIntelligenceClient(
            endpoint=self.endpoint,
            credential=AzureKeyCredential(self.key),
        )

    def _prepare_document(self, image: bytes) -> bytes:
        """Create an Azure-safe OCR copy while leaving the stored original unchanged."""
        is_webp = len(image) >= 12 and image[:4] == b"RIFF" and image[8:12] == b"WEBP"
        if len(image) <= self.max_document_bytes and not is_webp:
            return image

        try:
            with Image.open(BytesIO(image)) as source:
                prepared = ImageOps.exif_transpose(source)
                prepared.load()
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise OcrProcessingError(
                "The receipt image could not be prepared for Azure OCR"
            ) from exc

        if prepared.mode in {"RGBA", "LA"} or (
            prepared.mode == "P" and "transparency" in prepared.info
        ):
            rgba = prepared.convert("RGBA")
            background = Image.new("RGB", rgba.size, "white")
            background.paste(rgba, mask=rgba.getchannel("A"))
            prepared = background
        else:
            prepared = prepared.convert("RGB")

        max_dimension = 10_000
        if max(prepared.size) > max_dimension:
            prepared.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

        quality = 92
        while True:
            output = BytesIO()
            prepared.save(
                output,
                format="JPEG",
                quality=quality,
                optimize=True,
                progressive=True,
            )
            optimized = output.getvalue()
            if len(optimized) <= self.max_document_bytes:
                return optimized
            if quality > 40:
                quality -= 8
                continue

            width, height = prepared.size
            if width <= 640 or height <= 640:
                break
            prepared = prepared.resize(
                (max(640, width * 3 // 4), max(640, height * 3 // 4)),
                Image.Resampling.LANCZOS,
            )
            quality = 84

        raise OcrProcessingError(
            "Receipt image cannot be compressed below the Azure OCR size limit"
        )

    @staticmethod
    def _field_value(field: Any, key: str, attribute: str) -> Any:
        if field is None:
            return None
        value = getattr(field, attribute, None)
        if value is not None:
            return value
        getter = getattr(field, "get", None)
        return getter(key) if getter is not None else None

    @classmethod
    def _currency(cls, field: Any) -> tuple[Decimal | None, str | None]:
        value = cls._field_value(field, "valueCurrency", "value_currency")
        if value is None:
            return None, None
        getter = getattr(value, "get", None)
        amount = getattr(value, "amount", None)
        code = getattr(value, "currency_code", None)
        if getter is not None:
            amount = amount if amount is not None else getter("amount")
            code = code if code is not None else getter("currencyCode")
        try:
            parsed_amount = (
                Decimal(str(amount)).quantize(Decimal("0.01"))
                if amount is not None
                else None
            )
        except InvalidOperation:
            parsed_amount = None
        return parsed_amount, str(code).upper() if code else None

    @classmethod
    def _number(cls, field: Any) -> Decimal | None:
        value = cls._field_value(field, "valueNumber", "value_number")
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None

    @classmethod
    def _address(cls, field: Any) -> str | None:
        if field is None:
            return None
        direct = cls._field_value(field, "valueString", "value_string")
        if direct:
            return " ".join(str(direct).split())
        content = getattr(field, "content", None)
        getter = getattr(field, "get", None)
        if content is None and getter is not None:
            content = getter("content")
        if content:
            return ", ".join(
                part.strip() for part in str(content).splitlines() if part.strip()
            )
        address = cls._field_value(field, "valueAddress", "value_address")
        if address is None:
            return None
        address_get = getattr(address, "get", None)

        def part(attribute: str, key: str) -> Any:
            value = getattr(address, attribute, None)
            return value if value is not None else (
                address_get(key) if address_get is not None else None
            )

        street = part("street_address", "streetAddress")
        postal_code = part("postal_code", "postalCode")
        city = part("city", "city")
        values = [street, " ".join(str(value) for value in (postal_code, city) if value)]
        rendered = ", ".join(str(value).strip() for value in values if value)
        return rendered or None

    @classmethod
    def _line_items(cls, fields: dict[str, Any]) -> tuple[OcrLineItem, ...]:
        item_fields = (
            cls._field_value(fields.get("Items"), "valueArray", "value_array") or []
        )
        extracted: list[OcrLineItem] = []
        for item_field in item_fields:
            values = cls._field_value(item_field, "valueObject", "value_object") or {}
            description = cls._field_value(
                values.get("Description"), "valueString", "value_string"
            )
            quantity = cls._number(values.get("Quantity"))
            unit_price, _ = cls._currency(values.get("Price"))
            line_total, _ = cls._currency(values.get("TotalPrice"))
            if line_total is None and quantity is not None and unit_price is not None:
                line_total = (quantity * unit_price).quantize(Decimal("0.01"))
            if not description or line_total is None:
                continue
            extracted.append(
                OcrLineItem(
                    description=str(description)[:500],
                    quantity=quantity,
                    unit_price=unit_price,
                    line_total=line_total,
                )
            )
        return tuple(extracted)

    def extract_text(self, image: bytes) -> OcrResult:
        if self.client is None:
            raise OcrProcessingError(
                "Azure OCR is selected but its endpoint or key is missing"
            )
        try:
            document = self._prepare_document(image)
            poller = self.client.begin_analyze_document(
                "prebuilt-receipt",
                body=BytesIO(document),
                locale=self.locale or None,
            )
            result = poller.result(timeout=self.timeout_seconds)
        except Exception as exc:
            message = str(exc).strip() or type(exc).__name__
            raise OcrProcessingError(
                f"Azure Document Intelligence failed: {message[:400]}"
            ) from exc

        documents = getattr(result, "documents", None) or []
        if not documents:
            raise OcrProcessingError("Azure completed but did not recognize a receipt")
        fields = getattr(documents[0], "fields", None) or {}
        merchant = self._field_value(
            fields.get("MerchantName"), "valueString", "value_string"
        )
        purchase_date = self._field_value(
            fields.get("TransactionDate"), "valueDate", "value_date"
        )
        total, currency = self._currency(fields.get("Total"))
        subtotal, subtotal_currency = self._currency(fields.get("Subtotal"))
        tax, tax_currency = self._currency(fields.get("TotalTax"))
        tip, tip_currency = self._currency(fields.get("Tip"))
        currency = currency or subtotal_currency or tax_currency or tip_currency
        merchant_address = self._address(fields.get("MerchantAddress"))
        merchant_phone = self._field_value(
            fields.get("MerchantPhoneNumber"),
            "valuePhoneNumber",
            "value_phone_number",
        ) or self._field_value(
            fields.get("MerchantPhoneNumber"), "valueString", "value_string"
        )
        transaction_time = self._field_value(
            fields.get("TransactionTime"), "valueTime", "value_time"
        )
        raw_text = (getattr(result, "content", None) or "").strip()
        if not raw_text:
            raw_text = "\n".join(
                str(value)
                for value in (merchant, purchase_date, total)
                if value is not None
            )
        return OcrResult(
            provider="azure-document-intelligence",
            raw_text=raw_text,
            suggestions=ReceiptSuggestions(
                merchant_name=str(merchant)[:200] if merchant else None,
                purchase_date=(
                    purchase_date if isinstance(purchase_date, date) else None
                ),
                currency=currency,
                total=total,
                merchant_address=(
                    str(merchant_address)[:500] if merchant_address else None
                ),
                merchant_phone=(str(merchant_phone)[:100] if merchant_phone else None),
                transaction_time=(
                    transaction_time if isinstance(transaction_time, time) else None
                ),
                subtotal=subtotal,
                tax=tax,
                tip=tip,
            ),
            provider_payload=self._json_payload(result),
            line_items=self._line_items(fields),
        )

    @staticmethod
    def _json_payload(result: Any) -> dict[str, object] | None:
        as_dict = getattr(result, "as_dict", None)
        if as_dict is None:
            return None
        payload = as_dict()
        if not isinstance(payload, dict):
            return None
        return json.loads(json.dumps(payload, default=str))
