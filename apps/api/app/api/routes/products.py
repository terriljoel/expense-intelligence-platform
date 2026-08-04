from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentPrincipal, get_current_principal
from app.db.session import get_db_session
from app.core.config import Settings, get_settings
from app.product_intelligence.orchestration import (
    EnrichmentCandidateNotFoundError,
    confirm_enrichment_candidate,
    enrich_receipt_item,
)
from app.schemas.product import (
    ProductCreate,
    ProductEnrichmentRequest,
    ProductEnrichmentResponse,
    BarcodeDetectionResponse,
    ProductMatchConfirm,
    ProductMatchResponse,
    ProductResponse,
)
from app.services.barcode_decoder import (
    BarcodeImageValidationError,
    decode_barcode,
    validate_barcode_image,
)
from app.services.product import (
    ProductConflictError,
    ProductNotFoundError,
    ReceiptItemNotFoundError,
    confirm_product_match,
    create_product,
    list_products,
    get_item_context,
    match_receipt_item,
)


router = APIRouter(tags=["products"])


def _match_response(match: object) -> ProductMatchResponse:
    return ProductMatchResponse(
        product=ProductResponse.model_validate(match.product)
        if match.product
        else None,
        status=match.status,
        method=match.method,
        confidence=match.confidence,
    )


@router.post(
    "/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED
)
def post_product(
    payload: ProductCreate,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> ProductResponse:
    try:
        product = create_product(
            session,
            household_id=principal.household_id,
            **payload.model_dump(),
        )
    except ProductConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Product already exists") from exc
    return ProductResponse.model_validate(product)


@router.get("/products", response_model=list[ProductResponse])
def get_products(
    query: str | None = Query(default=None, max_length=200),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> list[ProductResponse]:
    return [
        ProductResponse.model_validate(product)
        for product in list_products(
            session, household_id=principal.household_id, query=query
        )
    ]


@router.post(
    "/receipt-items/{item_id}/product-match", response_model=ProductMatchResponse
)
def post_product_match(
    item_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> ProductMatchResponse:
    try:
        return _match_response(
            match_receipt_item(
                session, household_id=principal.household_id, item_id=item_id
            )
        )
    except ReceiptItemNotFoundError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Receipt item not found"
        ) from exc


@router.post(
    "/receipt-items/{item_id}/product-match/confirm",
    response_model=ProductMatchResponse,
)
def post_product_match_confirmation(
    item_id: UUID,
    payload: ProductMatchConfirm,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> ProductMatchResponse:
    try:
        match = confirm_product_match(
            session,
            household_id=principal.household_id,
            item_id=item_id,
            product_id=payload.product_id,
            user_id=principal.user_id,
        )
    except ReceiptItemNotFoundError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Receipt item not found"
        ) from exc
    except ProductNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found") from exc
    return _match_response(match)


@router.post(
    "/receipt-items/{item_id}/barcode-detect",
    response_model=BarcodeDetectionResponse,
)
async def post_barcode_detection(
    item_id: UUID,
    file: Annotated[UploadFile, File()],
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> BarcodeDetectionResponse:
    content = await file.read(settings.receipt_image_max_bytes + 1)
    media_type = file.content_type
    await file.close()
    try:
        get_item_context(session, principal.household_id, item_id)
        validate_barcode_image(
            content, media_type, settings.receipt_image_max_bytes
        )
        barcode, barcode_format, error = decode_barcode(content)
    except ReceiptItemNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Receipt item not found") from exc
    except BarcodeImageValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return BarcodeDetectionResponse(
        detected_barcode=barcode,
        barcode_format=barcode_format,
        error_message=error,
    )


@router.post(
    "/receipt-items/{item_id}/enrich", response_model=ProductEnrichmentResponse
)
def post_product_enrichment(
    item_id: UUID,
    payload: ProductEnrichmentRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> ProductEnrichmentResponse:
    if not settings.product_enrichment_enabled:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Product enrichment is disabled"
        )
    try:
        result = enrich_receipt_item(
            session,
            household_id=principal.household_id,
            item_id=item_id,
            barcode=payload.barcode,
            settings=settings,
        )
    except ReceiptItemNotFoundError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Receipt item not found"
        ) from exc
    return ProductEnrichmentResponse(
        run_id=result.run_id,
        status=result.status,
        match=_match_response(result.match),
        candidates=[candidate.as_dict() for candidate in result.candidates],
        errors=result.errors,
        agent_decision=result.agent_decision,
        providers_queried=result.providers_queried or [],
        ai_used=result.ai_used,
        retailer_web_search_performed=result.retailer_web_search_performed,
    )


@router.post(
    "/receipt-items/{item_id}/enrich/{run_id}/candidates/{candidate_index}/confirm",
    response_model=ProductMatchResponse,
)
def post_enrichment_candidate_confirmation(
    item_id: UUID,
    run_id: UUID,
    candidate_index: int,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> ProductMatchResponse:
    try:
        match = confirm_enrichment_candidate(
            session,
            household_id=principal.household_id,
            item_id=item_id,
            run_id=run_id,
            candidate_index=candidate_index,
            user_id=principal.user_id,
        )
    except (EnrichmentCandidateNotFoundError, ReceiptItemNotFoundError) as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Enrichment candidate not found"
        ) from exc
    return _match_response(match)
