from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_principal
from app.db.seed import seed_development_data
from app.db.session import engine, get_db_session
from app.main import app
from app.models import AuthSession, User, UserCredential
from app.services.auth import SESSION_COOKIE_NAME


TEST_PASSWORD = "correct-horse-battery-staple"
TEST_EMAIL = "auth-owner@example.test"


@pytest.fixture
def auth_client() -> Generator[TestClient, None, None]:
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection)
        seed = seed_development_data(session)
        user = session.get(User, seed.user_id)
        assert user is not None
        user.email = TEST_EMAIL
        credential = session.get(UserCredential, seed.user_id)
        if credential is None:
            credential = UserCredential(
                user_id=seed.user_id,
                password_hash=PasswordHash.recommended().hash(TEST_PASSWORD),
            )
            session.add(credential)
        else:
            credential.password_hash = PasswordHash.recommended().hash(
                TEST_PASSWORD
            )
        session.flush()

        def override_session() -> Generator[Session, None, None]:
            yield session

        app.dependency_overrides[get_db_session] = override_session
        app.dependency_overrides.pop(get_current_principal, None)
        try:
            with TestClient(app) as client:
                yield client
        finally:
            app.dependency_overrides.clear()
            session.close()
            transaction.rollback()


def test_login_me_logout_and_protected_route(auth_client: TestClient) -> None:
    before_login = auth_client.get("/receipts")
    login = auth_client.post(
        "/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )

    assert before_login.status_code == 401
    assert login.status_code == 200
    assert login.json()["email"] == TEST_EMAIL
    cookie = login.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert "expense_session=" in cookie
    assert TEST_PASSWORD not in cookie

    me = auth_client.get("/auth/me")
    receipts = auth_client.get("/receipts")
    logout = auth_client.post("/auth/logout")
    after_logout = auth_client.get("/receipts")

    assert me.status_code == 200
    assert me.json()["role"] == "owner"
    assert receipts.status_code == 200
    assert logout.status_code == 204
    assert after_logout.status_code == 401


def test_invalid_login_and_cross_site_login_are_rejected(
    auth_client: TestClient,
) -> None:
    invalid = auth_client.post(
        "/auth/login",
        json={"email": TEST_EMAIL, "password": "wrong"},
    )
    cross_site = auth_client.post(
        "/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        headers={
            "Origin": "https://attacker.example",
            "Sec-Fetch-Site": "cross-site",
        },
    )

    assert invalid.status_code == 401
    assert invalid.json() == {"detail": "Invalid email or password"}
    assert cross_site.status_code == 403


def test_expired_session_is_rejected(auth_client: TestClient) -> None:
    token = "expired-test-session-token"
    seed = seed_development_data(
        next(app.dependency_overrides[get_db_session]())
    )
    session = next(app.dependency_overrides[get_db_session]())
    session.add(
        AuthSession(
            user_id=seed.user_id,
            household_id=seed.household_id,
            token_hash=sha256(token.encode()).hexdigest(),
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
    )
    session.flush()
    auth_client.cookies.set(SESSION_COOKIE_NAME, token)

    response = auth_client.get("/auth/me")

    assert response.status_code == 401


def test_user_can_create_and_switch_between_isolated_households(
    auth_client: TestClient,
) -> None:
    login = auth_client.post(
        "/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    original_household_id = login.json()["household_id"]
    original_receipt = auth_client.post(
        "/receipts",
        json={
            "purchase_date": "2026-07-23",
            "currency": "EUR",
            "stated_total": "8.00",
        },
    )
    created_household = auth_client.post(
        "/auth/households",
        json={"name": "Shared Apartment", "default_currency": "EUR"},
    )
    second_household_id = created_household.json()["household_id"]

    households = auth_client.get("/auth/households")
    switched = auth_client.post(
        f"/auth/switch-household/{second_household_id}"
    )
    second_receipts_before = auth_client.get("/receipts")
    second_receipt = auth_client.post(
        "/receipts",
        json={
            "purchase_date": "2026-07-23",
            "currency": "EUR",
            "stated_total": "19.00",
        },
    )
    forbidden = auth_client.post(f"/auth/switch-household/{uuid4()}")
    switched_back = auth_client.post(
        f"/auth/switch-household/{original_household_id}"
    )
    original_receipts_after = auth_client.get("/receipts")

    assert original_receipt.status_code == 201
    assert created_household.status_code == 201
    household_ids = {
        item["household_id"] for item in households.json()
    }
    assert {original_household_id, second_household_id}.issubset(
        household_ids
    )
    assert switched.status_code == 200
    assert switched.json()["household_id"] == second_household_id
    assert second_receipts_before.json() == []
    assert second_receipt.status_code == 201
    assert forbidden.status_code == 403
    assert switched_back.status_code == 200
    original_ids = {item["id"] for item in original_receipts_after.json()}
    assert original_receipt.json()["id"] in original_ids
    assert second_receipt.json()["id"] not in original_ids
