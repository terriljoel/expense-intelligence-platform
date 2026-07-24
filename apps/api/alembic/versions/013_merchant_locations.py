"""Make merchant identity branch-aware by address.

Revision ID: 013_merchant_locations
Revises: 012_receipt_ocr_items
Create Date: 2026-07-23
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "013_merchant_locations"
down_revision: str | None = "012_receipt_ocr_items"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("merchants", sa.Column("address", sa.Text(), nullable=True))
    op.add_column(
        "merchants",
        sa.Column(
            "normalized_address",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
        ),
    )
    op.drop_constraint(
        "merchants_normalized_name_unique",
        "merchants",
        type_="unique",
    )
    op.create_unique_constraint(
        "merchants_identity_unique",
        "merchants",
        ["household_id", "normalized_name", "normalized_address"],
    )


def downgrade() -> None:
    op.drop_constraint("merchants_identity_unique", "merchants", type_="unique")
    op.create_unique_constraint(
        "merchants_normalized_name_unique",
        "merchants",
        ["household_id", "normalized_name"],
    )
    op.drop_column("merchants", "normalized_address")
    op.drop_column("merchants", "address")
