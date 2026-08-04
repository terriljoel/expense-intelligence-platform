import re
import unicodedata


_UNIT_PATTERN = re.compile(r"(?<=\d)\s*(kg|g|mg|l|ml|cl)\b", re.IGNORECASE)
_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)


def normalize_text(value: str) -> str:
    """Create a stable comparison key without changing stored source text."""
    value = unicodedata.normalize("NFKC", value).casefold().strip()
    value = _UNIT_PATTERN.sub(lambda match: match.group(1).lower(), value)
    return " ".join(_NON_WORD.sub(" ", value).split())


def normalize_barcode(value: str | None) -> str | None:
    digits = re.sub(r"\D", "", value or "")
    return digits if 8 <= len(digits) <= 14 else None


normalize_product_name = normalize_text
normalize_receipt_item = normalize_text
