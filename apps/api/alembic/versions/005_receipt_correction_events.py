"""Add receipt correction and void audit event types.

Revision ID: 005_receipt_correction_events
Revises: 004_payment_method_identity
Create Date: 2026-07-22
"""

from collections.abc import Sequence

from alembic import op


revision: str = "005_receipt_correction_events"
down_revision: str | None = "004_payment_method_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "audit_events_type_valid",
        "audit_events",
        type_="check",
    )
    op.create_check_constraint(
        "audit_events_type_valid",
        "audit_events",
        "event_type IN ("
        "'receipt_created', 'receipt_updated', "
        "'item_added', 'item_updated', 'item_removed', "
        "'payment_added', 'payment_updated', 'payment_removed', "
        "'receipt_approved', 'receipt_voided'"
        ")",
    )


def downgrade() -> None:
    op.drop_constraint(
        "audit_events_type_valid",
        "audit_events",
        type_="check",
    )
    op.create_check_constraint(
        "audit_events_type_valid",
        "audit_events",
        "event_type IN ("
        "'receipt_created', 'item_added', "
        "'payment_added', 'receipt_approved'"
        ")",
    )
