"""Record the initial SQL schema as the Alembic baseline.

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-07-22
"""

from collections.abc import Sequence


revision: str = "001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """The schema was created by database/migrations/001_initial_schema.sql."""


def downgrade() -> None:
    """A baseline downgrade intentionally leaves existing schema objects intact."""
