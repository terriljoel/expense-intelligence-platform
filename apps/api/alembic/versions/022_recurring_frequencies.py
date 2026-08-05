"""Support daily, weekly, monthly, quarterly, and yearly recurring expenses."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "022_recurring_frequencies"
down_revision: str | None = "021_knowledge_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "recurring_expenses",
        sa.Column(
            "frequency",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'monthly'"),
        ),
    )
    op.create_check_constraint(
        "recurring_expenses_frequency_valid",
        "recurring_expenses",
        "frequency IN ('daily', 'weekly', 'monthly', 'quarterly', 'yearly')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "recurring_expenses_frequency_valid",
        "recurring_expenses",
        type_="check",
    )
    op.drop_column("recurring_expenses", "frequency")
