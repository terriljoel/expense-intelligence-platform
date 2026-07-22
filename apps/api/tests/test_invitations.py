from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentPrincipal, get_current_principal
from app.db.seed import seed_development_data
from app.db.session import engine, get_db_session
from app.main import app
from app.models import Household, HouseholdInvitation, HouseholdMember, User


MEMBER_PASSWORD = "second-member-password"
OWNER_EMAIL = "invitation-owner@example.test"


@pytest.fixture
def invitation_client() -> Generator[tuple[TestClient, Session], None, None]:
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection)
        seed = seed_development_data(session)
        owner = session.get(User, seed.user_id)
        assert owner is not None
        owner.email = OWNER_EMAIL
        session.flush()

        def override_session() -> Generator[Session, None, None]:
            yield session

        app.dependency_overrides[get_db_session] = override_session
        try:
            with TestClient(app) as client:
                yield client, session
        finally:
            app.dependency_overrides.clear()
            session.close()
            transaction.rollback()


def test_invited_member_can_join_and_see_shared_household_data(
    invitation_client: tuple[TestClient, Session],
) -> None:
    client, session = invitation_client
    receipt = client.post(
        "/receipts",
        json={
            "purchase_date": "2026-07-23",
            "currency": "EUR",
            "stated_total": "12.00",
        },
    ).json()
    income = client.post(
        "/income",
        json={
            "source": "Shared employer",
            "income_type": "salary",
            "received_date": "2026-07-23",
            "amount": "100.00",
            "currency": "EUR",
        },
    ).json()
    created = client.post(
        "/household/invitations",
        json={"email": "member@example.test", "role": "member"},
    )

    assert created.status_code == 201
    token = created.json()["invitation_token"]
    stored = session.get(HouseholdInvitation, created.json()["id"])
    assert stored is not None
    assert stored.token_hash != token

    preview = client.post("/invitations/preview", json={"token": token})
    accepted = client.post(
        "/invitations/accept",
        json={
            "token": token,
            "display_name": "Second Member",
            "password": MEMBER_PASSWORD,
        },
    )
    reused = client.post("/invitations/preview", json={"token": token})

    assert preview.status_code == 200
    assert preview.json()["household_name"] == "Personal Household"
    assert accepted.status_code == 200
    assert reused.status_code == 404

    app.dependency_overrides.pop(get_current_principal, None)
    login = client.post(
        "/auth/login",
        json={
            "email": "member@example.test",
            "password": MEMBER_PASSWORD,
        },
    )
    owner = session.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert owner is not None
    second_household = Household(
        name="Owner's Second Household",
        default_currency="EUR",
    )
    session.add(second_household)
    session.flush()
    session.add(
        HouseholdMember(
            household_id=second_household.id,
            user_id=owner.id,
            role="owner",
        )
    )
    session.flush()
    app.dependency_overrides[get_current_principal] = lambda: CurrentPrincipal(
        user_id=owner.id,
        household_id=second_household.id,
        role="owner",
    )
    existing_invitation = client.post(
        "/household/invitations",
        json={"email": "member@example.test", "role": "member"},
    )
    app.dependency_overrides.pop(get_current_principal, None)
    accepted_existing = client.post(
        "/invitations/accept-existing",
        json={"token": existing_invitation.json()["invitation_token"]},
    )
    member_households = client.get("/auth/households")
    receipts = client.get("/receipts")
    incomes = client.get("/income")
    members = client.get("/household/members")
    forbidden_invite = client.post(
        "/household/invitations",
        json={"email": "third@example.test", "role": "member"},
    )

    assert login.status_code == 200
    assert login.json()["role"] == "member"
    assert existing_invitation.status_code == 201
    assert accepted_existing.status_code == 200
    assert {
        household["household_id"] for household in member_households.json()
    } == {login.json()["household_id"], str(second_household.id)}
    assert receipt["id"] in {item["id"] for item in receipts.json()}
    assert income["id"] in {item["id"] for item in incomes.json()}
    assert {
        OWNER_EMAIL,
        "member@example.test",
    }.issubset({item["email"] for item in members.json()})
    assert forbidden_invite.status_code == 403


def test_duplicate_pending_invitation_is_rejected(
    invitation_client: tuple[TestClient, Session],
) -> None:
    client, _ = invitation_client
    payload = {"email": "pending@example.test", "role": "member"}

    first = client.post("/household/invitations", json=payload)
    duplicate = client.post("/household/invitations", json=payload)

    assert first.status_code == 201
    assert duplicate.status_code == 409
