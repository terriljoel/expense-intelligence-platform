"""Record the initial SQL schema as the Alembic baseline.

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-07-22
"""

from collections.abc import Sequence
from pathlib import Path

from alembic import op


revision: str = "001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the baseline on a fresh database; existing stamped databases skip it."""

    migration = next(
        (
            path
            for root in Path(__file__).resolve().parents
            if (path := root / "database" / "migrations" / "001_initial_schema.sql").is_file()
        ),
        None,
    )
    if migration is None:
        raise RuntimeError("database/migrations/001_initial_schema.sql was not found")
    op.execute(migration.read_text(encoding="utf-8"))


def downgrade() -> None:
    """A baseline downgrade intentionally leaves existing schema objects intact."""
