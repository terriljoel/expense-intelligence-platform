from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Merchant, Product, Receipt, ReceiptItem
from app.schemas.product import ProductInsightCounts
from app.services.product import ProductMatch, match_receipt_item


@dataclass(frozen=True)
class InsightRow:
    item: ReceiptItem
    receipt: Receipt
    merchant: Merchant | None
    product: Product | None


def product_insight_counts(
    session: Session, household_id: UUID
) -> ProductInsightCounts:
    statuses = dict(
        session.execute(
            select(ReceiptItem.product_match_status, func.count())
            .join(Receipt, Receipt.id == ReceiptItem.receipt_id)
            .where(
                ReceiptItem.household_id == household_id,
                ReceiptItem.line_type == "product",
                Receipt.status != "voided",
            )
            .group_by(ReceiptItem.product_match_status)
        ).all()
    )
    product_counts = session.execute(
        select(
            func.count(Product.id),
            func.count(Product.id).filter(Product.product_type == "food"),
            func.count(Product.id).filter(
                Product.product_type == "food", Product.nutrition != {}
            ),
        ).where(Product.household_id == household_id)
    ).one()
    return ProductInsightCounts(
        total=sum(statuses.values()),
        unmatched=statuses.get("unmatched", 0),
        suggested=statuses.get("suggested", 0),
        confirmed=statuses.get("confirmed", 0),
        ignored=statuses.get("rejected", 0),
        products=product_counts[0],
        food_products=product_counts[1],
        food_products_with_nutrition=product_counts[2],
    )


def list_product_insights(
    session: Session,
    household_id: UUID,
    *,
    status: str | None = None,
    query: str | None = None,
    merchant_id: UUID | None = None,
    limit: int = 100,
) -> list[InsightRow]:
    statement = (
        select(ReceiptItem, Receipt, Merchant, Product)
        .join(Receipt, Receipt.id == ReceiptItem.receipt_id)
        .join(Merchant, Merchant.id == Receipt.merchant_id, isouter=True)
        .join(Product, Product.id == ReceiptItem.product_id, isouter=True)
        .where(
            ReceiptItem.household_id == household_id,
            ReceiptItem.line_type == "product",
            Receipt.status != "voided",
        )
    )
    if status:
        statement = statement.where(ReceiptItem.product_match_status == status)
    if merchant_id:
        statement = statement.where(Receipt.merchant_id == merchant_id)
    if query and (term := query.strip()):
        pattern = f"%{term}%"
        statement = statement.where(
            or_(
                ReceiptItem.description.ilike(pattern),
                Product.canonical_name.ilike(pattern),
                Product.brand.ilike(pattern),
                Product.barcode == term,
                Merchant.name.ilike(pattern),
            )
        )
    rows = session.execute(
        statement.order_by(Receipt.purchase_date.desc(), ReceiptItem.position).limit(
            limit
        )
    ).all()
    return [InsightRow(*row) for row in rows]


def set_product_insight_status(
    session: Session,
    household_id: UUID,
    item_id: UUID,
    status: str,
) -> ReceiptItem | None:
    item = session.scalar(
        select(ReceiptItem).where(
            ReceiptItem.id == item_id,
            ReceiptItem.household_id == household_id,
            ReceiptItem.line_type == "product",
        )
    )
    if item is None:
        return None
    item.product_id = None
    item.product_match_status = status
    item.product_match_method = "user_ignored" if status == "rejected" else None
    item.product_match_confidence = None
    session.flush()
    return item


def bulk_local_match(
    session: Session, household_id: UUID, item_ids: list[UUID]
) -> tuple[int, int]:
    processed = matched = 0
    for item_id in dict.fromkeys(item_ids):
        result: ProductMatch = match_receipt_item(
            session, household_id=household_id, item_id=item_id
        )
        processed += 1
        matched += result.product is not None
    return processed, matched
