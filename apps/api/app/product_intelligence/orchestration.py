from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Merchant, Product, ProductEnrichmentRun, ProductEvidence
from app.product_intelligence.contracts import (
    ProductCandidate,
    ProductProvider,
    ProductQuery,
)
from app.product_intelligence.rankers import CandidateRanker
from app.product_intelligence.registry import configured_providers, configured_ranker
from app.product_intelligence.taxonomy import infer_family
from app.services.product import (
    ProductMatch,
    create_product,
    find_local_candidates,
    get_item_context,
    link_product_match,
    match_receipt_item,
)
from app.services.text_normalization import normalize_product_name


@dataclass(frozen=True)
class EnrichmentResult:
    run_id: UUID | None
    status: str
    match: ProductMatch
    candidates: list[ProductCandidate]
    errors: list[str]
    agent_decision: dict[str, object] | None = None
    providers_queried: list[str] | None = None
    ai_used: bool = False
    retailer_web_search_performed: bool = False


class EnrichmentCandidateNotFoundError(Exception):
    pass


def enrich_receipt_item(
    session: Session,
    *,
    household_id: UUID,
    item_id: UUID,
    barcode: str | None,
    settings: Settings,
    providers: list[ProductProvider] | None = None,
    ranker: CandidateRanker | None = None,
) -> EnrichmentResult:
    local = match_receipt_item(session, household_id=household_id, item_id=item_id)
    if local.product:
        return EnrichmentResult(None, "completed", local, [], [])

    item, receipt = get_item_context(session, household_id, item_id)
    merchant = session.get(Merchant, receipt.merchant_id) if receipt.merchant_id else None
    query = ProductQuery(
        description=item.description,
        barcode=barcode,
        merchant_name=merchant.name if merchant else None,
        merchant_address=merchant.address if merchant else receipt.merchant_address,
    )
    run = ProductEnrichmentRun(
        household_id=household_id,
        receipt_item_id=item_id,
        status="running",
        strategy="provider_registry",
        request_data={
            "description": item.description,
            "barcode": barcode,
            "merchant_name": query.merchant_name,
        },
        started_at=datetime.now(timezone.utc),
    )
    session.add(run)
    session.flush()

    local_candidates = find_local_candidates(
        session,
        household_id=household_id,
        item=item,
        receipt=receipt,
        threshold=settings.product_fuzzy_match_threshold,
        limit=settings.product_max_local_candidates,
    )
    active_providers = (
        providers if providers is not None else configured_providers(settings)
    )
    external_candidates, errors = _collect(active_providers, query)
    candidates = [
        _with_family(candidate) for candidate in local_candidates + external_candidates
    ]
    decision_data = None
    active_ranker = ranker or configured_ranker(settings)
    if active_ranker and candidates and not barcode:
        try:
            decision = active_ranker.rank(query, candidates)
            decision_data = asdict(decision)
            if decision.should_match:
                chosen = candidates.pop(decision.selected_index)
                candidates.insert(
                    0,
                    replace(
                        chosen,
                        canonical_name=decision.canonical_name or chosen.canonical_name,
                        family_name=decision.family_name or chosen.family_name,
                        category=decision.category or chosen.category,
                        confidence=min(0.91, decision.confidence),
                    ),
                )
        except Exception as exc:
            errors.append(f"agent_ranker: {type(exc).__name__}")
    best = max(candidates, key=lambda candidate: candidate.confidence, default=None)
    match = ProductMatch(None)
    if (
        best
        and barcode
        and best.provider != "local_knowledge"
        and best.confidence >= settings.product_auto_match_threshold
    ):
        product = _materialize(session, household_id, best)
        match = link_product_match(
            session,
            item=item,
            receipt=receipt,
            product=product,
            confidence=Decimal(str(best.confidence)),
            method=f"{best.provider}_barcode" if barcode else best.provider,
        )
        _record_evidence(session, household_id, product, best)
        run.status = "completed"
    elif best and best.confidence >= settings.product_review_threshold:
        item.product_match_status = "suggested"
        item.product_match_method = best.provider
        item.product_match_confidence = Decimal(str(best.confidence))
        match = ProductMatch(
            None, "suggested", best.provider, item.product_match_confidence
        )
        run.status = "review"
    else:
        run.status = "failed" if errors and not candidates else "completed"

    run.result_data = {
        "candidates": [candidate.as_dict() for candidate in candidates],
        "errors": errors,
        "agent_decision": decision_data,
    }
    run.error_message = "; ".join(errors)[:2000] or None
    run.completed_at = datetime.now(timezone.utc)
    session.flush()
    return EnrichmentResult(
        run.id,
        run.status,
        match,
        candidates,
        errors,
        decision_data,
        [provider.name for provider in active_providers],
        decision_data is not None,
        not barcode
        and any(provider.name == "tavily_web" for provider in active_providers),
    )


def _with_family(candidate: ProductCandidate) -> ProductCandidate:
    if candidate.family_name:
        return candidate
    family, category = infer_family(
        candidate.canonical_name, candidate.description, candidate.category
    )
    return replace(
        candidate,
        family_name=family,
        category=candidate.category or category,
    )


def _collect(
    providers: list[ProductProvider], query: ProductQuery
) -> tuple[list[ProductCandidate], list[str]]:
    candidates: list[ProductCandidate] = []
    errors: list[str] = []
    for provider in providers:
        try:
            candidates.extend(provider.search(query))
        except Exception as exc:  # provider failures must not break receipt data
            errors.append(f"{provider.name}: {type(exc).__name__}")
    return candidates, errors


def _materialize(
    session: Session, household_id: UUID, candidate: ProductCandidate
) -> Product:
    if candidate.product_id:
        product = session.scalar(
            select(Product).where(
                Product.id == UUID(candidate.product_id),
                Product.household_id == household_id,
            )
        )
        if product:
            return product
        raise EnrichmentCandidateNotFoundError
    statement = select(Product).where(Product.household_id == household_id)
    identity = (
        Product.barcode == candidate.barcode
        if candidate.barcode
        else Product.normalized_name == normalize_product_name(candidate.canonical_name)
    )
    existing = session.scalar(statement.where(identity))
    if existing:
        return existing
    return create_product(
        session,
        household_id=household_id,
        **{
            key: value
            for key, value in candidate.as_dict().items()
            if key
            in {
                "canonical_name",
                "description",
                "brand",
                "manufacturer",
                "family_name",
                "product_type",
                "category",
                "barcode",
                "metadata",
                "nutrition",
            }
        },
    )


def confirm_enrichment_candidate(
    session: Session,
    *,
    household_id: UUID,
    item_id: UUID,
    run_id: UUID,
    candidate_index: int,
    user_id: UUID,
) -> ProductMatch:
    run = session.scalar(
        select(ProductEnrichmentRun).where(
            ProductEnrichmentRun.id == run_id,
            ProductEnrichmentRun.household_id == household_id,
            ProductEnrichmentRun.receipt_item_id == item_id,
        )
    )
    candidates = run.result_data.get("candidates") if run else None
    if not isinstance(candidates, list) or not 0 <= candidate_index < len(candidates):
        raise EnrichmentCandidateNotFoundError
    candidate_data = candidates[candidate_index]
    if not isinstance(candidate_data, dict):
        raise EnrichmentCandidateNotFoundError

    candidate = ProductCandidate(**candidate_data)
    item, receipt = get_item_context(session, household_id, item_id)
    product = _materialize(session, household_id, candidate)
    match = link_product_match(
        session,
        item=item,
        receipt=receipt,
        product=product,
        confidence=Decimal("1"),
        method=f"user_confirmed_{candidate.provider}",
        user_id=user_id,
    )
    if candidate.provider != "local_knowledge":
        _record_evidence(session, household_id, product, candidate)
    run.status = "completed"
    run.result_data = {**run.result_data, "selected_candidate_index": candidate_index}
    run.completed_at = datetime.now(timezone.utc)
    session.flush()
    return match


def _record_evidence(
    session: Session, household_id: UUID, product: Product, candidate: ProductCandidate
) -> None:
    session.add(
        ProductEvidence(
            household_id=household_id,
            product_id=product.id,
            provider=candidate.provider,
            source_url=candidate.source_url,
            external_id=candidate.external_id,
            confidence=Decimal(str(candidate.confidence)),
            evidence_data=candidate.as_dict(),
        )
    )
