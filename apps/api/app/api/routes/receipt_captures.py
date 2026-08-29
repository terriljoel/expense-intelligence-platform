from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.dependencies import (
    CurrentPrincipal,
    get_current_principal,
    get_receipt_image_storage,
)
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.schemas.receipt_capture import ReceiptCaptureResponse
from app.services.receipt_capture import (
    ALLOWED_IMAGE_TYPES,
    CaptureAlreadyUsedError,
    CaptureNotFoundError,
    CaptureValidationError,
    DuplicateCaptureError,
    OcrProvider,
    capture_image_bytes,
    create_capture,
    delete_capture,
    get_capture,
    get_ocr_provider,
    process_capture_ocr,
)
from app.services.receipt_image_storage import (
    ReceiptImageNotFoundError,
    ReceiptImageStorage,
    ReceiptImageStorageError,
)


router = APIRouter(prefix="/receipt-captures", tags=["receipt captures"])


@router.get("/upload-policy")
def get_upload_policy(
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    return {
        "max_bytes": settings.receipt_image_max_bytes,
        "max_megabytes": round(settings.receipt_image_max_bytes / (1024 * 1024), 1),
        "allowed_media_types": sorted(ALLOWED_IMAGE_TYPES),
    }


def _capture_response(capture: object, *, reused: bool = False) -> ReceiptCaptureResponse:
    response = ReceiptCaptureResponse.model_validate(capture)
    return response.model_copy(
        update={
            "image_url": f"/receipt-captures/{response.id}/image",
            "reused": reused,
        }
    )


@router.post(
    "",
    response_model=ReceiptCaptureResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_receipt_capture(
    response: Response,
    file: Annotated[UploadFile, File()],
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    storage: ReceiptImageStorage = Depends(get_receipt_image_storage),
) -> ReceiptCaptureResponse:
    content = await file.read(settings.receipt_image_max_bytes + 1)
    await file.close()
    try:
        capture, created = create_capture(
            session,
            settings=settings,
            storage=storage,
            household_id=principal.household_id,
            uploaded_by_user_id=principal.user_id,
            filename=file.filename,
            media_type=file.content_type,
            content=content,
        )
    except CaptureValidationError as exc:
        error_status = (
            status.HTTP_413_CONTENT_TOO_LARGE
            if len(content) > settings.receipt_image_max_bytes
            else status.HTTP_422_UNPROCESSABLE_CONTENT
        )
        raise HTTPException(
            status_code=error_status,
            detail=str(exc),
        ) from exc
    except DuplicateCaptureError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This receipt image was already captured in the household",
        ) from exc
    except ReceiptImageStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    if not created:
        response.status_code = status.HTTP_200_OK
    return _capture_response(capture, reused=not created)


@router.get("/{capture_id}", response_model=ReceiptCaptureResponse)
def get_receipt_capture(
    capture_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> ReceiptCaptureResponse:
    try:
        capture = get_capture(
            session,
            household_id=principal.household_id,
            capture_id=capture_id,
        )
    except CaptureNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt capture not found",
        ) from exc
    return _capture_response(capture)


@router.get("/{capture_id}/image", response_class=Response)
def get_receipt_capture_image(
    capture_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    storage: ReceiptImageStorage = Depends(get_receipt_image_storage),
) -> Response:
    try:
        capture = get_capture(
            session,
            household_id=principal.household_id,
            capture_id=capture_id,
        )
        image = capture_image_bytes(capture, storage)
    except (CaptureNotFoundError, ReceiptImageNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt capture not found",
        ) from exc
    except ReceiptImageStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    filename = capture.original_filename or f"{capture.id}"
    return Response(
        content=image,
        media_type=capture.media_type,
        headers={
            "Content-Disposition": (
                f"inline; filename*=UTF-8''{quote(filename, safe='')}"
            )
        },
    )


@router.post("/{capture_id}/ocr", response_model=ReceiptCaptureResponse)
def post_receipt_capture_ocr(
    capture_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    provider: OcrProvider = Depends(get_ocr_provider),
    storage: ReceiptImageStorage = Depends(get_receipt_image_storage),
) -> ReceiptCaptureResponse:
    try:
        capture = process_capture_ocr(
            session,
            storage=storage,
            provider=provider,
            household_id=principal.household_id,
            capture_id=capture_id,
        )
    except CaptureNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt capture not found",
        ) from exc
    except CaptureAlreadyUsedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Receipt capture is already linked to a receipt",
        ) from exc
    return _capture_response(capture)


@router.delete("/{capture_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_receipt_capture(
    capture_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    storage: ReceiptImageStorage = Depends(get_receipt_image_storage),
) -> None:
    try:
        delete_capture(
            session,
            storage=storage,
            household_id=principal.household_id,
            capture_id=capture_id,
        )
    except CaptureNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt capture not found",
        ) from exc
    except CaptureAlreadyUsedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A linked receipt capture cannot be deleted",
        ) from exc
    except ReceiptImageStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
