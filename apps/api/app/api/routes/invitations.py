from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.dependencies import (
    CurrentPrincipal,
    get_current_principal,
    reject_cross_site_request,
    require_global_admin,
    require_household_admin,
)
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.models import AuthSession, Household, HouseholdMember, User, UserCredential
from app.schemas.household import (
    HouseholdResponse,
    HouseholdUpdate,
    MemberPasswordReset,
    MemberRoleUpdate,
)
from app.schemas.invitation import (
    HouseholdMemberResponse,
    InvitationAccept,
    InvitationAcceptedResponse,
    InvitationCreate,
    InvitationCreatedResponse,
    InvitationPreviewResponse,
    InvitationResponse,
    InvitationTokenRequest,
)
from app.services.invitation import (
    InvitationConflictError,
    InvitationNotFoundError,
    accept_invitation,
    accept_existing_user_invitation,
    cancel_invitation,
    create_invitation,
    list_members,
    list_pending_invitations,
    preview_invitation,
)
from app.services.household import (
    HouseholdMemberNotFoundError,
    HouseholdPermissionError,
    LastOwnerError,
    SelfRemovalError,
    deactivate_member,
    get_household,
    leave_household,
    update_household,
    update_member_role,
)
from app.services.auth import SESSION_COOKIE_NAME, password_hash


household_router = APIRouter(prefix="/household", tags=["household"])
invitation_router = APIRouter(prefix="/invitations", tags=["invitations"])


def _household_response(
    *,
    household: Household,
    role: str,
) -> HouseholdResponse:
    return HouseholdResponse(
        household_id=household.id,
        name=household.name,
        default_currency=household.default_currency,
        role=role,
        created_at=household.created_at,
        updated_at=household.updated_at,
    )


def _member_response(
    *,
    membership: HouseholdMember,
    user: User,
) -> HouseholdMemberResponse:
    return HouseholdMemberResponse(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=membership.role,
        joined_at=membership.joined_at,
    )


@household_router.get("", response_model=HouseholdResponse)
def get_current_household(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> HouseholdResponse:
    household = get_household(
        session, household_id=principal.household_id
    )
    return _household_response(household=household, role=principal.role)


@household_router.patch("", response_model=HouseholdResponse)
def patch_current_household(
    payload: HouseholdUpdate,
    principal: CurrentPrincipal = Depends(require_household_admin),
    session: Session = Depends(get_db_session),
) -> HouseholdResponse:
    household = update_household(
        session,
        household_id=principal.household_id,
        changes=payload.model_dump(exclude_unset=True),
    )
    return _household_response(household=household, role=principal.role)


@household_router.get("/members", response_model=list[HouseholdMemberResponse])
def get_household_members(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> list[HouseholdMemberResponse]:
    return [
        HouseholdMemberResponse(
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=membership.role,
            joined_at=membership.joined_at,
        )
        for membership, user in list_members(
            session, household_id=principal.household_id
        )
    ]


@household_router.patch(
    "/members/{user_id}",
    response_model=HouseholdMemberResponse,
)
def patch_household_member(
    user_id: UUID,
    payload: MemberRoleUpdate,
    principal: CurrentPrincipal = Depends(require_household_admin),
    session: Session = Depends(get_db_session),
) -> HouseholdMemberResponse:
    try:
        membership = update_member_role(
            session,
            household_id=principal.household_id,
            actor_user_id=principal.user_id,
            actor_role=principal.role,
            target_user_id=user_id,
            new_role=payload.role,
        )
    except HouseholdMemberNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active household member not found",
        ) from exc
    except HouseholdPermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an owner can manage owner access or their own role",
        ) from exc
    except LastOwnerError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Promote another owner before changing the last owner",
        ) from exc
    user = session.get(User, membership.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return _member_response(membership=membership, user=user)


@household_router.put(
    "/members/{user_id}/password",
    status_code=status.HTTP_204_NO_CONTENT,
)
def reset_household_member_password(
    user_id: UUID,
    payload: MemberPasswordReset,
    principal: CurrentPrincipal = Depends(require_global_admin),
    session: Session = Depends(get_db_session),
) -> None:
    membership = session.get(
        HouseholdMember,
        {"household_id": principal.household_id, "user_id": user_id},
    )
    if membership is None or not membership.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active household member not found",
        )
    credential = session.get(UserCredential, user_id)
    if credential is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Password login is not configured for this member",
        )
    credential.password_hash = password_hash.hash(payload.password)
    session.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
    session.flush()


@household_router.delete(
    "/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_household_member(
    user_id: UUID,
    principal: CurrentPrincipal = Depends(require_household_admin),
    session: Session = Depends(get_db_session),
) -> None:
    try:
        deactivate_member(
            session,
            household_id=principal.household_id,
            actor_user_id=principal.user_id,
            actor_role=principal.role,
            target_user_id=user_id,
        )
    except HouseholdMemberNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active household member not found",
        ) from exc
    except HouseholdPermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot remove this household owner",
        ) from exc
    except SelfRemovalError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Use the leave-household action for your own membership",
        ) from exc
    except LastOwnerError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The last household owner cannot be removed",
        ) from exc


@household_router.post(
    "/leave",
    status_code=status.HTTP_204_NO_CONTENT,
)
def post_leave_household(
    response: Response,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> None:
    try:
        leave_household(
            session,
            household_id=principal.household_id,
            user_id=principal.user_id,
        )
    except LastOwnerError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Promote another owner before leaving this household",
        ) from exc
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="strict",
    )


@household_router.post(
    "/invitations",
    response_model=InvitationCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_household_invitation(
    payload: InvitationCreate,
    principal: CurrentPrincipal = Depends(require_household_admin),
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> InvitationCreatedResponse:
    try:
        invitation, token = create_invitation(
            session,
            household_id=principal.household_id,
            invited_by_user_id=principal.user_id,
            email=payload.email,
            role=payload.role,
            invitation_hours=settings.invitation_hours,
        )
    except InvitationConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This person is already a member or has a pending invitation",
        ) from exc
    return InvitationCreatedResponse(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
        invitation_token=token,
    )


@household_router.get(
    "/invitations", response_model=list[InvitationResponse]
)
def get_household_invitations(
    principal: CurrentPrincipal = Depends(require_household_admin),
    session: Session = Depends(get_db_session),
) -> list[InvitationResponse]:
    return [
        InvitationResponse.model_validate(invitation)
        for invitation in list_pending_invitations(
            session, household_id=principal.household_id
        )
    ]


@household_router.delete(
    "/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_household_invitation(
    invitation_id: UUID,
    principal: CurrentPrincipal = Depends(require_household_admin),
    session: Session = Depends(get_db_session),
) -> None:
    try:
        cancel_invitation(
            session,
            household_id=principal.household_id,
            invitation_id=invitation_id,
        )
    except InvitationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pending invitation not found",
        ) from exc


@invitation_router.post(
    "/preview", response_model=InvitationPreviewResponse
)
def post_invitation_preview(
    payload: InvitationTokenRequest,
    request: Request,
    session: Session = Depends(get_db_session),
) -> InvitationPreviewResponse:
    reject_cross_site_request(request)
    try:
        invitation, household = preview_invitation(
            session, token=payload.token
        )
    except InvitationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation is invalid or expired",
        ) from exc
    return InvitationPreviewResponse(
        email=invitation.email,
        household_name=household.name,
        role=invitation.role,
        expires_at=invitation.expires_at,
        existing_account=session.scalar(
            select(User.id).where(func.lower(User.email) == invitation.email)
        )
        is not None,
    )


@invitation_router.post(
    "/accept", response_model=InvitationAcceptedResponse
)
def post_invitation_acceptance(
    payload: InvitationAccept,
    request: Request,
    session: Session = Depends(get_db_session),
) -> InvitationAcceptedResponse:
    reject_cross_site_request(request)
    try:
        invitation = accept_invitation(
            session,
            token=payload.token,
            display_name=payload.display_name,
            password=payload.password,
        )
    except InvitationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation is invalid or expired",
        ) from exc
    except InvitationConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account already exists for this email",
        ) from exc
    return InvitationAcceptedResponse(
        email=invitation.email,
        household_id=invitation.household_id,
        message="Account created. Sign in with your new password.",
    )


@invitation_router.post(
    "/accept-existing", response_model=InvitationAcceptedResponse
)
def post_existing_user_invitation_acceptance(
    payload: InvitationTokenRequest,
    request: Request,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> InvitationAcceptedResponse:
    reject_cross_site_request(request)
    try:
        invitation = accept_existing_user_invitation(
            session,
            token=payload.token,
            user_id=principal.user_id,
        )
    except InvitationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation is invalid or expired",
        ) from exc
    except InvitationConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sign in with the email address that received this invitation",
        ) from exc
    return InvitationAcceptedResponse(
        email=invitation.email,
        household_id=invitation.household_id,
        message="Household joined.",
    )
