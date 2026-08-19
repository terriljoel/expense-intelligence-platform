from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentPrincipal, get_current_principal
from app.db.seed import SeedResult, seed_development_data
from app.db.session import engine, get_db_session
from app.main import app
from app.models import AuthSession, Household, HouseholdMember, User, UserCredential
from app.services.auth import password_hash
from app.services.invitation import (
    accept_existing_user_invitation,
    create_invitation,
)
from app.services.payment_method import create_payment_method


@dataclass(frozen=True)
class HouseholdAdminContext:
    client: TestClient
    session: Session
    seed: SeedResult


@pytest.fixture
def household_admin_context() -> Generator[HouseholdAdminContext, None, None]:
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection)
        seed = seed_development_data(session)

        def override_session() -> Generator[Session, None, None]:
            yield session

        def owner_principal() -> CurrentPrincipal:
            return CurrentPrincipal(
                user_id=seed.user_id,
                household_id=seed.household_id,
                role="owner",
            )

        app.dependency_overrides[get_db_session] = override_session
        app.dependency_overrides[get_current_principal] = owner_principal
        try:
            with TestClient(app) as client:
                yield HouseholdAdminContext(client, session, seed)
        finally:
            app.dependency_overrides.clear()
            session.close()
            transaction.rollback()


def _add_member(
    session: Session, *, household_id: UUID
) -> tuple[User, HouseholdMember]:
    user = User(
        auth_subject=f"household-admin-test:{uuid4()}",
        email=f"{uuid4()}@example.test",
        display_name="Household Test Member",
    )
    session.add(user)
    session.flush()
    membership = HouseholdMember(
        household_id=household_id,
        user_id=user.id,
        role="member",
    )
    session.add(membership)
    session.flush()
    return user, membership


def test_owner_can_manage_settings_roles_and_remove_member_safely(
    household_admin_context: HouseholdAdminContext,
) -> None:
    context = household_admin_context
    member, membership = _add_member(
        context.session,
        household_id=context.seed.household_id,
    )
    settings = context.client.patch(
        "/household",
        json={"name": "Managed Household", "default_currency": "GBP"},
    )
    promoted = context.client.patch(
        f"/household/members/{member.id}",
        json={"role": "owner"},
    )
    demoted = context.client.patch(
        f"/household/members/{member.id}",
        json={"role": "member"},
    )
    app.dependency_overrides[get_current_principal] = lambda: CurrentPrincipal(
        user_id=member.id,
        household_id=context.seed.household_id,
        role="member",
    )
    created_receipt = context.client.post(
        "/receipts",
        json={
            "purchase_date": "2026-07-23",
            "currency": "GBP",
            "stated_total": "7.00",
        },
    )
    app.dependency_overrides[get_current_principal] = lambda: CurrentPrincipal(
        user_id=context.seed.user_id,
        household_id=context.seed.household_id,
        role="owner",
    )
    removed = context.client.delete(f"/household/members/{member.id}")
    active_members = context.client.get("/household/members")
    receipts = context.client.get("/receipts")
    context.session.refresh(membership)

    assert settings.status_code == 200
    assert settings.json()["name"] == "Managed Household"
    assert settings.json()["default_currency"] == "GBP"
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "owner"
    assert demoted.status_code == 200
    assert created_receipt.status_code == 201
    assert removed.status_code == 204
    assert membership.is_active is False
    assert str(member.id) not in {
        item["user_id"] for item in active_members.json()
    }
    preserved = next(
        item
        for item in receipts.json()
        if item["id"] == created_receipt.json()["id"]
    )
    assert preserved["created_by_display_name"] == member.display_name


def test_last_owner_cannot_be_demoted_removed_or_leave(
    household_admin_context: HouseholdAdminContext,
) -> None:
    context = household_admin_context
    household = Household(name="Single Owner Household", default_currency="EUR")
    context.session.add(household)
    context.session.flush()
    context.session.add(
        HouseholdMember(
            household_id=household.id,
            user_id=context.seed.user_id,
            role="owner",
        )
    )
    context.session.flush()
    app.dependency_overrides[get_current_principal] = lambda: CurrentPrincipal(
        user_id=context.seed.user_id,
        household_id=household.id,
        role="owner",
    )
    demoted = context.client.patch(
        f"/household/members/{context.seed.user_id}",
        json={"role": "member"},
    )
    removed = context.client.delete(
        f"/household/members/{context.seed.user_id}"
    )
    left = context.client.post("/household/leave")

    assert demoted.status_code == 409
    assert removed.status_code == 409
    assert left.status_code == 409


def test_removed_member_can_be_invited_back(
    household_admin_context: HouseholdAdminContext,
) -> None:
    context = household_admin_context
    member, membership = _add_member(
        context.session,
        household_id=context.seed.household_id,
    )
    removed = context.client.delete(f"/household/members/{member.id}")
    invitation, token = create_invitation(
        context.session,
        household_id=context.seed.household_id,
        invited_by_user_id=context.seed.user_id,
        email=member.email or "",
        role="member",
        invitation_hours=24,
    )
    accepted = accept_existing_user_invitation(
        context.session,
        token=token,
        user_id=member.id,
    )
    context.session.refresh(membership)

    assert removed.status_code == 204
    assert accepted.id == invitation.id
    assert membership.is_active is True
    assert membership.role == "member"


def test_owner_can_reset_single_household_member_password_and_revoke_sessions(
    household_admin_context: HouseholdAdminContext,
) -> None:
    context = household_admin_context
    member, _ = _add_member(
        context.session,
        household_id=context.seed.household_id,
    )
    credential = UserCredential(
        user_id=member.id,
        password_hash=password_hash.hash("old-member-password"),
    )
    context.session.add(credential)
    context.session.add(
        AuthSession(
            household_id=context.seed.household_id,
            user_id=member.id,
            token_hash="a" * 64,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    context.session.flush()
    app.dependency_overrides[get_current_principal] = lambda: CurrentPrincipal(
        user_id=context.seed.user_id,
        household_id=context.seed.household_id,
        role="owner",
        is_global_admin=True,
    )

    response = context.client.put(
        f"/household/members/{member.id}/password",
        json={"password": "new-member-password"},
    )
    context.session.refresh(credential)

    assert response.status_code == 204
    assert password_hash.verify("new-member-password", credential.password_hash)
    assert (
        context.session.query(AuthSession)
        .filter(AuthSession.user_id == member.id)
        .count()
        == 0
    )


def test_global_admin_can_reset_multi_household_account(
    household_admin_context: HouseholdAdminContext,
) -> None:
    context = household_admin_context
    member, _ = _add_member(
        context.session,
        household_id=context.seed.household_id,
    )
    other = Household(name="Other Household", default_currency="EUR")
    context.session.add(other)
    context.session.flush()
    app.dependency_overrides[get_current_principal] = lambda: CurrentPrincipal(
        user_id=context.seed.user_id,
        household_id=context.seed.household_id,
        role="owner",
        is_global_admin=True,
    )
    context.session.add(
        HouseholdMember(household_id=other.id, user_id=member.id, role="member")
    )
    context.session.add(
        UserCredential(
            user_id=member.id,
            password_hash=password_hash.hash("old-member-password"),
        )
    )
    context.session.flush()

    response = context.client.put(
        f"/household/members/{member.id}/password",
        json={"password": "new-member-password"},
    )

    assert response.status_code == 204


def test_owner_can_manage_member_methods_and_record_member_payment(
    household_admin_context: HouseholdAdminContext,
) -> None:
    context = household_admin_context
    member, _ = _add_member(context.session, household_id=context.seed.household_id)
    member_method = create_payment_method(
        context.session,
        household_id=context.seed.household_id,
        user_id=member.id,
        name="Member Visa",
        method_type="credit_card",
        provider="Member Bank",
        last_four="4321",
    )
    owner_method = context.client.post(
        "/payment-methods",
        json={"name": "Owner Cash", "method_type": "cash"},
    ).json()

    visible = context.client.get("/payment-methods").json()
    receipt = context.client.post(
        "/receipts",
        json={
            "purchase_date": "2026-08-19",
            "currency": "EUR",
            "stated_total": "5.00",
            "payment_method_id": str(member_method.id),
        },
    ).json()
    payment = context.client.get(f"/receipts/{receipt['id']}/payments").json()[0]
    edited_payment = context.client.patch(
        f"/receipts/{receipt['id']}/payments/{payment['id']}",
        json={"amount": "4.00"},
    )
    edited_method = context.client.patch(
        f"/payment-methods/{member_method.id}", json={"name": "Member Card"}
    )

    assert member_method.id in {UUID(method["id"]) for method in visible}
    assert payment["user_id"] == str(member.id)
    assert edited_payment.status_code == 200
    assert edited_payment.json()["amount"] == "4.00"
    assert edited_method.status_code == 200
    assert edited_method.json()["name"] == "Member Card"

    app.dependency_overrides[get_current_principal] = lambda: CurrentPrincipal(
        user_id=member.id,
        household_id=context.seed.household_id,
        role="member",
    )
    member_visible = context.client.get("/payment-methods").json()
    forbidden_owner_edit = context.client.patch(
        f"/payment-methods/{owner_method['id']}", json={"name": "Not allowed"}
    )

    assert {method["user_id"] for method in member_visible} == {str(member.id)}
    assert forbidden_owner_edit.status_code == 404
