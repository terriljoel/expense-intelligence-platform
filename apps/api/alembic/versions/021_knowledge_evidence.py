"""Preserve product source documents and extracted knowledge facts."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "021_knowledge_evidence"
down_revision: str | None = "020_recurring_expenses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "household_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("households.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("product_id", postgresql.UUID(as_uuid=True)),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text()),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content_text", sa.Text()),
        sa.Column("raw_object_key", sa.Text()),
        sa.Column(
            "content_type", sa.Text(), nullable=False, server_default="text/markdown"
        ),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "retrieved_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["product_id", "household_id"],
            ["products.id", "products.household_id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "id", "household_id", name="knowledge_documents_id_household_unique"
        ),
        sa.UniqueConstraint(
            "household_id",
            "product_id",
            "content_sha256",
            name="knowledge_documents_content_unique",
        ),
    )
    op.create_index(
        "knowledge_documents_product_retrieved_idx",
        "knowledge_documents",
        ["product_id", sa.text("retrieved_at DESC")],
    )
    op.create_table(
        "knowledge_facts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("household_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fact_type", sa.Text(), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("extraction_method", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column(
            "confirmation_status", sa.Text(), nullable=False, server_default="suggested"
        ),
        sa.Column(
            "confirmed_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "household_id"],
            ["knowledge_documents.id", "knowledge_documents.household_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id", "household_id"],
            ["products.id", "products.household_id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="knowledge_facts_confidence_valid",
        ),
        sa.CheckConstraint(
            "confirmation_status IN ('suggested', 'confirmed', 'rejected')",
            name="knowledge_facts_status_valid",
        ),
        sa.UniqueConstraint(
            "document_id", "fact_type", name="knowledge_facts_document_type_unique"
        ),
    )
    op.create_index(
        "knowledge_facts_product_type_idx",
        "knowledge_facts",
        ["product_id", "fact_type"],
    )


def downgrade() -> None:
    op.drop_table("knowledge_facts")
    op.drop_table("knowledge_documents")
