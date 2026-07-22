from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi import Request
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.services.auth import SESSION_COOKIE_NAME, resolve_auth_session


@dataclass(frozen=True)
class CurrentPrincipal:
    user_id: UUID
    household_id: UUID
    role: str


def reject_cross_site_request(request: Request) -> None:
    """Reject browser state changes that originate outside this application."""

    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-site request rejected",
        )
    source = request.headers.get("origin")
    if source is None and request.headers.get("referer"):
        parts = urlsplit(request.headers["referer"])
        source = f"{parts.scheme}://{parts.netloc}"
    if source is not None:
        target = f"{request.url.scheme}://{request.headers.get('host', '')}"
        if source.rstrip("/") != target.rstrip("/"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Request origin does not match this application",
            )


def get_current_principal(
    request: Request,
    session: Session = Depends(get_db_session),
) -> CurrentPrincipal:
    """Resolve the current user and household from a server-side session."""

    reject_cross_site_request(request)
    token = request.cookies.get(SESSION_COOKIE_NAME)
    authenticated = (
        resolve_auth_session(session, token=token) if token else None
    )
    if authenticated is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    return CurrentPrincipal(
        user_id=authenticated.user_id,
        household_id=authenticated.household_id,
        role=authenticated.role,
    )


def require_household_admin(
    principal: CurrentPrincipal = Depends(get_current_principal),
) -> CurrentPrincipal:
    if principal.role not in {"owner", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner or admin role required",
        )
    return principal
