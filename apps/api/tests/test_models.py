from sqlalchemy.orm import configure_mappers

from app.db.base import Base
from app.models import (
    AuditEvent,
    AuthSession,
    Household,
    HouseholdInvitation,
    HouseholdMember,
    IncomeEntry,
    Merchant,
    PaymentMethod,
    Receipt,
    ReceiptItem,
    ReceiptPayment,
    User,
    UserCredential,
)


def test_all_expected_tables_are_registered() -> None:
    expected_tables = {
        "users",
        "households",
        "household_members",
        "household_invitations",
        "merchants",
        "payment_methods",
        "receipts",
        "receipt_items",
        "receipt_payments",
        "audit_events",
        "income_entries",
        "auth_sessions",
        "user_credentials",
    }

    assert set(Base.metadata.tables) == expected_tables


def test_all_mappers_can_be_configured() -> None:
    configure_mappers()


def test_models_use_expected_table_names() -> None:
    models = (
        AuditEvent,
        AuthSession,
        User,
        Household,
        HouseholdInvitation,
        HouseholdMember,
        IncomeEntry,
        Merchant,
        PaymentMethod,
        Receipt,
        ReceiptItem,
        ReceiptPayment,
        UserCredential,
    )

    assert {model.__tablename__ for model in models} == set(Base.metadata.tables)
