from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import (
    CurrentPrincipal,
    get_current_principal,
    reject_cross_site_request,
)
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.schemas.auth import (
    AuthenticatedUserResponse,
    HouseholdAccessResponse,
    HouseholdCreateRequest,
    LoginRequest,
)
from app.services.auth import (
    SESSION_COOKIE_NAME,
    HouseholdAccessError,
    InvalidCredentialsError,
    authenticate_password,
    create_household,
    create_auth_session,
    list_user_households,
    resolve_auth_session,
    revoke_auth_session,
    switch_auth_session_household,
)


router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/login", response_model=AuthenticatedUserResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> AuthenticatedUserResponse:
    reject_cross_site_request(request)
    try:
        user, membership = authenticate_password(
            session,
            email=payload.email,
            password=payload.password,
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        ) from exc
    token, auth_session = create_auth_session(
        session,
        user=user,
        membership=membership,
        session_hours=settings.auth_session_hours,
    )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    return AuthenticatedUserResponse(
        user_id=user.id,
        household_id=membership.household_id,
        email=user.email or payload.email,
        display_name=user.display_name,
        role=membership.role,
        is_global_admin=user.is_global_admin,
        session_expires_at=auth_session.expires_at,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    _: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        revoke_auth_session(session, token=token)
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="strict",
    )


@router.get("/me", response_model=AuthenticatedUserResponse)
def get_me(
    request: Request,
    _: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> AuthenticatedUserResponse:
    token = request.cookies[SESSION_COOKIE_NAME]
    authenticated = resolve_auth_session(session, token=token)
    if authenticated is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return AuthenticatedUserResponse(
        user_id=authenticated.user_id,
        household_id=authenticated.household_id,
        email=authenticated.email,
        display_name=authenticated.display_name,
        role=authenticated.role,
        is_global_admin=authenticated.is_global_admin,
        session_expires_at=authenticated.expires_at,
    )


@router.get(
    "/households",
    response_model=list[HouseholdAccessResponse],
)
def get_households(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> list[HouseholdAccessResponse]:
    return [
        HouseholdAccessResponse(
            household_id=household.id,
            name=household.name,
            default_currency=household.default_currency,
            role=membership.role,
            is_active=household.id == principal.household_id,
        )
        for household, membership in list_user_households(
            session, user_id=principal.user_id
        )
    ]


@router.post(
    "/households",
    response_model=HouseholdAccessResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_household(
    payload: HouseholdCreateRequest,
    request: Request,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> HouseholdAccessResponse:
    reject_cross_site_request(request)
    household, membership = create_household(
        session,
        user_id=principal.user_id,
        name=payload.name,
        default_currency=payload.default_currency,
    )
    return HouseholdAccessResponse(
        household_id=household.id,
        name=household.name,
        default_currency=household.default_currency,
        role=membership.role,
        is_active=False,
    )


@router.post(
    "/switch-household/{household_id}",
    response_model=AuthenticatedUserResponse,
)
def switch_household(
    household_id: UUID,
    request: Request,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> AuthenticatedUserResponse:
    reject_cross_site_request(request)
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    try:
        switch_auth_session_household(
            session,
            token=token,
            user_id=principal.user_id,
            household_id=household_id,
        )
    except HouseholdAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this household",
        ) from exc
    authenticated = resolve_auth_session(session, token=token)
    if authenticated is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return AuthenticatedUserResponse(
        user_id=authenticated.user_id,
        household_id=authenticated.household_id,
        email=authenticated.email,
        display_name=authenticated.display_name,
        role=authenticated.role,
        is_global_admin=authenticated.is_global_admin,
        session_expires_at=authenticated.expires_at,
    )
