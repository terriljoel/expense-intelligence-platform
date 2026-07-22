"""Prevent duplicate active payment methods.

Revision ID: 004_payment_method_identity
Revises: 003_audit_event_sequence
Create Date: 2026-07-22
"""

from collections.abc import Sequence

from alembic import op


revision: str = "004_payment_method_identity"
down_revision: str | None = "003_audit_event_sequence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE UNIQUE INDEX payment_methods_active_identity_unique
        ON payment_methods (
            household_id,
            user_id,
            lower(btrim(name)),
            method_type,
            lower(btrim(COALESCE(provider, ''))),
            COALESCE(last_four, '')
        )
        WHERE is_active
        """
    )


def downgrade() -> None:
    op.drop_index(
        "payment_methods_active_identity_unique",
        table_name="payment_methods",
    )
