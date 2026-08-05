import re
import unicodedata
from difflib import SequenceMatcher


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


def product_search_terms(value: str) -> list[str]:
    return [normalize_text(value)]


def product_search_similarity(query: str, candidate: str) -> float:
    transliteration = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
    candidate_key = normalize_text(candidate).translate(transliteration)
    return max(
        SequenceMatcher(None, term.translate(transliteration), candidate_key).ratio()
        for term in product_search_terms(query)
    )
