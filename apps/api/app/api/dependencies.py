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
    is_global_admin: bool = False


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
        forwarded_host = request.headers.get("x-forwarded-host")
        forwarded_proto = request.headers.get("x-forwarded-proto")
        host = forwarded_host or request.headers.get("host", "")
        scheme = forwarded_proto or request.url.scheme
        target = f"{scheme}://{host}"
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
        is_global_admin=authenticated.is_global_admin,
    )


def require_household_admin(
    principal: CurrentPrincipal = Depends(get_current_principal),
) -> CurrentPrincipal:
    if principal.role != "owner" and not principal.is_global_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Household owner or global administrator required",
        )
    return principal


def require_global_admin(
    principal: CurrentPrincipal = Depends(get_current_principal),
) -> CurrentPrincipal:
    if not principal.is_global_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Global administrator role required",
        )
    return principal
