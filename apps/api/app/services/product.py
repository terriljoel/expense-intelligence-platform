from dataclasses import dataclass
from decimal import Decimal
from difflib import SequenceMatcher
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Product, ProductAlias, Receipt, ReceiptItem
from app.product_intelligence.contracts import ProductCandidate
from app.services.text_normalization import normalize_product_name


class ProductNotFoundError(Exception):
    pass


class ReceiptItemNotFoundError(Exception):
    pass


class ProductConflictError(Exception):
    pass


@dataclass(frozen=True)
class ProductMatch:
    product: Product | None
    status: str = "unmatched"
    method: str | None = None
    confidence: Decimal | None = None


def create_product(
    session: Session, *, household_id: UUID, **values: object
) -> Product:
    normalized_name = normalize_product_name(str(values["canonical_name"]))
    barcode = values.get("barcode")
    identity = (
        Product.barcode == barcode
        if barcode
        else Product.normalized_name == normalized_name
    )
    if session.scalar(
        select(Product.id).where(Product.household_id == household_id, identity)
    ):
        raise ProductConflictError
    product = Product(
        household_id=household_id,
        normalized_name=normalized_name,
        metadata_=values.pop("metadata", {}),
        **values,
    )
    session.add(product)
    try:
        session.flush()
    except IntegrityError as exc:
        raise ProductConflictError from exc
    return product


def list_products(
    session: Session, *, household_id: UUID, query: str | None = None
) -> list[Product]:
    statement = select(Product).where(Product.household_id == household_id)
    if query:
        term = f"%{normalize_product_name(query)}%"
        statement = statement.where(
            or_(Product.normalized_name.ilike(term), Product.barcode == query)
        )
    return list(session.scalars(statement.order_by(Product.normalized_name).limit(100)))


def get_item_context(
    session: Session, household_id: UUID, item_id: UUID
) -> tuple[ReceiptItem, Receipt]:
    row = session.execute(
        select(ReceiptItem, Receipt)
        .join(Receipt, Receipt.id == ReceiptItem.receipt_id)
        .where(ReceiptItem.id == item_id, ReceiptItem.household_id == household_id)
    ).one_or_none()
    if row is None:
        raise ReceiptItemNotFoundError
    return row


def match_receipt_item(
    session: Session, *, household_id: UUID, item_id: UUID
) -> ProductMatch:
    item, receipt = get_item_context(session, household_id, item_id)
    if item.product_id:
        return ProductMatch(
            session.get(Product, item.product_id),
            item.product_match_status,
            item.product_match_method,
            item.product_match_confidence,
        )
    alias = session.scalar(
        select(ProductAlias)
        .where(
            ProductAlias.household_id == household_id,
            ProductAlias.normalized_description == item.normalized_description,
            or_(
                ProductAlias.merchant_id == receipt.merchant_id,
                ProductAlias.merchant_id.is_(None),
            ),
        )
        .order_by(ProductAlias.merchant_id.is_(None), ProductAlias.confidence.desc())
    )
    if alias is None:
        return ProductMatch(None)
    product = session.get(Product, alias.product_id)
    item.product_id, item.product_match_status = alias.product_id, "confirmed"
    item.product_match_method, item.product_match_confidence = (
        "confirmed_alias",
        alias.confidence,
    )
    session.flush()
    return ProductMatch(product, "confirmed", "confirmed_alias", alias.confidence)


def find_local_candidates(
    session: Session,
    *,
    household_id: UUID,
    item: ReceiptItem,
    receipt: Receipt,
    threshold: float,
    limit: int,
) -> list[ProductCandidate]:
    """Rank learned aliases; fuzzy results always require human confirmation."""
    rows = session.execute(
        select(ProductAlias, Product)
        .join(Product, Product.id == ProductAlias.product_id)
        .where(ProductAlias.household_id == household_id)
    ).all()
    best: dict[UUID, ProductCandidate] = {}
    for alias, product in rows:
        score, evidence = _alias_similarity_details(
            item.normalized_description,
            alias.normalized_description,
            same_merchant=alias.merchant_id == receipt.merchant_id,
        )
        if score < threshold:
            continue
        candidate = ProductCandidate(
            product_id=str(product.id),
            canonical_name=product.canonical_name,
            provider="local_knowledge",
            confidence=score,
            barcode=product.barcode,
            description=product.description,
            brand=product.brand,
            manufacturer=product.manufacturer,
            family_name=product.family_name,
            product_type=product.product_type,
            category=product.category,
            metadata=product.metadata_,
            nutrition=product.nutrition,
            evidence=evidence,
        )
        if product.id not in best or score > best[product.id].confidence:
            best[product.id] = candidate
    return sorted(
        best.values(), key=lambda candidate: candidate.confidence, reverse=True
    )[:limit]


def _alias_similarity_details(
    left: str, right: str, *, same_merchant: bool
) -> tuple[float, dict[str, object]]:
    left_tokens, right_tokens = set(left.split()), set(right.split())
    union = left_tokens | right_tokens
    token_score = len(left_tokens & right_tokens) / len(union) if union else 0
    string_score = SequenceMatcher(None, left, right).ratio()
    score = 0.7 * string_score + 0.3 * token_score
    confidence = round(min(0.91, score + (0.05 if same_merchant else 0)), 3)
    return confidence, {
        "level": "possible" if confidence >= 0.8 else "weak",
        "string_similarity": round(string_score, 3),
        "token_similarity": round(token_score, 3),
        "same_merchant": same_merchant,
        "score_formula": "70% string + 30% word overlap + 5% same merchant; capped at 91%",
        "reason": "Previously confirmed household knowledge",
        "ai_generated": False,
    }


def _alias_similarity(left: str, right: str, *, same_merchant: bool) -> float:
    """Backward-compatible score helper used by tests and callers."""

    return _alias_similarity_details(left, right, same_merchant=same_merchant)[0]


def confirm_product_match(
    session: Session,
    *,
    household_id: UUID,
    item_id: UUID,
    product_id: UUID,
    user_id: UUID,
) -> ProductMatch:
    item, receipt = get_item_context(session, household_id, item_id)
    product = session.scalar(
        select(Product).where(
            Product.id == product_id, Product.household_id == household_id
        )
    )
    if product is None:
        raise ProductNotFoundError
    return link_product_match(
        session,
        item=item,
        receipt=receipt,
        product=product,
        confidence=Decimal("1"),
        method="user_confirmed",
        user_id=user_id,
    )


def link_product_match(
    session: Session,
    *,
    item: ReceiptItem,
    receipt: Receipt,
    product: Product,
    confidence: Decimal,
    method: str,
    user_id: UUID | None = None,
) -> ProductMatch:
    alias = session.scalar(
        select(ProductAlias).where(
            ProductAlias.household_id == item.household_id,
            ProductAlias.merchant_id == receipt.merchant_id,
            ProductAlias.normalized_description == item.normalized_description,
        )
    )
    if alias is None:
        alias = ProductAlias(
            household_id=item.household_id,
            merchant_id=receipt.merchant_id,
            product_id=product.id,
            raw_description=item.description,
            normalized_description=item.normalized_description,
            confidence=confidence,
            match_method=method,
            confirmed_by_user_id=user_id,
        )
        session.add(alias)
    else:
        alias.product_id, alias.confidence = product.id, confidence
        alias.match_method, alias.confirmed_by_user_id = method, user_id
    item.product_id, item.product_match_status = product.id, "confirmed"
    item.product_match_method, item.product_match_confidence = method, confidence
    session.flush()
    return ProductMatch(product, "confirmed", method, confidence)
