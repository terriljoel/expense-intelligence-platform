"""Add deterministic audit event ordering.

Revision ID: 003_audit_event_sequence
Revises: 002_audit_events
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "003_audit_event_sequence"
down_revision: str | None = "002_audit_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "audit_events",
        sa.Column(
            "sequence_number",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
    )
    op.create_unique_constraint(
        "audit_events_sequence_number_key",
        "audit_events",
        ["sequence_number"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "audit_events_sequence_number_key",
        "audit_events",
        type_="unique",
    )
    op.drop_column("audit_events", "sequence_number")
