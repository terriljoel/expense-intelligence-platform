import hashlib
import json
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KnowledgeDocument, KnowledgeFact, Product
from app.product_intelligence.contracts import ProductCandidate


def record_candidate_knowledge(
    session: Session,
    *,
    household_id: UUID,
    product: Product,
    candidate: ProductCandidate,
    user_id: UUID,
) -> KnowledgeDocument:
    evidence = dict(candidate.evidence)
    content = str(evidence.pop("source_content", "")) or json.dumps(
        {**candidate.as_dict(), "evidence": evidence}, ensure_ascii=False, default=str
    )
    digest = hashlib.sha256(content.encode()).hexdigest()
    document = session.scalar(
        select(KnowledgeDocument).where(
            KnowledgeDocument.household_id == household_id,
            KnowledgeDocument.product_id == product.id,
            KnowledgeDocument.content_sha256 == digest,
        )
    )
    if document is None:
        document = KnowledgeDocument(
            household_id=household_id,
            product_id=product.id,
            provider=candidate.provider,
            source_url=candidate.source_url,
            title=candidate.canonical_name,
            content_text=content,
            content_type="text/markdown"
            if candidate.provider == "tavily_web"
            else "application/json",
            content_sha256=digest,
            metadata_={"external_id": candidate.external_id, "evidence": evidence},
        )
        session.add(document)
        session.flush()
    existing = set(
        session.scalars(
            select(KnowledgeFact.fact_type).where(
                KnowledgeFact.document_id == document.id
            )
        )
    )
    values: dict[str, object] = {
        "brand": candidate.brand,
        "manufacturer": candidate.manufacturer,
        "family_name": candidate.family_name,
        "category": candidate.category,
        "barcode": candidate.barcode,
        "nutrition": candidate.nutrition or None,
        "metadata": candidate.metadata or None,
    }
    for fact_type, value in values.items():
        if value is None or fact_type in existing:
            continue
        session.add(
            KnowledgeFact(
                household_id=household_id,
                document_id=document.id,
                product_id=product.id,
                fact_type=fact_type,
                value=value if isinstance(value, dict) else {"value": value},
                extraction_method=candidate.provider,
                confidence=Decimal(str(candidate.confidence)),
                confirmation_status="confirmed",
                confirmed_by_user_id=user_id,
            )
        )
    session.flush()
    return document


def product_knowledge(
    session: Session, *, household_id: UUID, product_id: UUID
) -> tuple[Product | None, list[tuple[KnowledgeDocument, list[KnowledgeFact]]]]:
    product = session.scalar(
        select(Product).where(
            Product.id == product_id, Product.household_id == household_id
        )
    )
    if product is None:
        return None, []
    documents = list(
        session.scalars(
            select(KnowledgeDocument)
            .where(
                KnowledgeDocument.household_id == household_id,
                KnowledgeDocument.product_id == product_id,
            )
            .order_by(KnowledgeDocument.retrieved_at.desc())
        )
    )
    facts = session.scalars(
        select(KnowledgeFact).where(
            KnowledgeFact.household_id == household_id,
            KnowledgeFact.product_id == product_id,
        )
    ).all()
    by_document: dict[UUID, list[KnowledgeFact]] = {}
    for fact in facts:
        by_document.setdefault(fact.document_id, []).append(fact)
    return product, [
        (document, by_document.get(document.id, [])) for document in documents
    ]
