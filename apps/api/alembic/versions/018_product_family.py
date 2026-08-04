"""Add semantic product families.

Revision ID: 018_product_family
Revises: 017_product_intelligence
Create Date: 2026-08-03
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "018_product_family"
down_revision: str | None = "017_product_intelligence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("family_name", sa.Text()))
    op.create_index(
        "products_household_family_idx", "products", ["household_id", "family_name"]
    )


def downgrade() -> None:
    op.drop_index("products_household_family_idx", table_name="products")
    op.drop_column("products", "family_name")
