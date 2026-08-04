"""Add household product knowledge and receipt-item matching.

Revision ID: 017_product_intelligence
Revises: 016_receipt_duplicates
Create Date: 2026-08-02
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "017_product_intelligence"
down_revision: str | None = "016_receipt_duplicates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    json = postgresql.JSONB(astext_type=sa.Text())
    op.create_table(
        "products",
        sa.Column(
            "id", uuid, server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("household_id", uuid, nullable=False),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("brand", sa.Text()),
        sa.Column("manufacturer", sa.Text()),
        sa.Column("product_type", sa.Text(), server_default="other", nullable=False),
        sa.Column("category", sa.Text()),
        sa.Column("barcode", sa.Text()),
        sa.Column(
            "metadata", json, server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column(
            "nutrition", json, server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "btrim(canonical_name) <> ''", name="products_name_not_blank"
        ),
        sa.CheckConstraint(
            "btrim(normalized_name) <> ''", name="products_normalized_name_not_blank"
        ),
        sa.CheckConstraint(
            "barcode IS NULL OR barcode ~ '^[0-9]{8,14}$'",
            name="products_barcode_valid",
        ),
        sa.ForeignKeyConstraint(
            ["household_id"], ["households.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "household_id", name="products_id_household_unique"),
    )
    op.create_index(
        "products_household_name_idx", "products", ["household_id", "normalized_name"]
    )
    op.create_index(
        "products_household_barcode_unique",
        "products",
        ["household_id", "barcode"],
        unique=True,
        postgresql_where=sa.text("barcode IS NOT NULL"),
    )
    op.create_index(
        "products_household_name_no_barcode_unique",
        "products",
        ["household_id", "normalized_name"],
        unique=True,
        postgresql_where=sa.text("barcode IS NULL"),
    )

    op.add_column("receipt_items", sa.Column("normalized_description", sa.Text()))
    op.execute(
        "UPDATE receipt_items SET normalized_description = lower(regexp_replace(btrim(description), '\\s+', ' ', 'g'))"
    )
    op.alter_column("receipt_items", "normalized_description", nullable=False)
    op.add_column("receipt_items", sa.Column("product_id", uuid))
    op.add_column(
        "receipt_items",
        sa.Column(
            "product_match_status",
            sa.Text(),
            server_default="unmatched",
            nullable=False,
        ),
    )
    op.add_column("receipt_items", sa.Column("product_match_method", sa.Text()))
    op.add_column(
        "receipt_items", sa.Column("product_match_confidence", sa.Numeric(4, 3))
    )
    op.create_unique_constraint(
        "receipt_items_id_household_unique", "receipt_items", ["id", "household_id"]
    )
    op.create_foreign_key(
        "receipt_items_product_scope_fk",
        "receipt_items",
        "products",
        ["product_id", "household_id"],
        ["id", "household_id"],
    )
    op.create_check_constraint(
        "receipt_items_product_match_status_valid",
        "receipt_items",
        "product_match_status IN ('unmatched', 'suggested', 'confirmed', 'rejected')",
    )
    op.create_check_constraint(
        "receipt_items_product_match_confidence_valid",
        "receipt_items",
        "product_match_confidence IS NULL OR (product_match_confidence >= 0 AND product_match_confidence <= 1)",
    )

    op.create_table(
        "product_aliases",
        sa.Column(
            "id", uuid, server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("household_id", uuid, nullable=False),
        sa.Column("merchant_id", uuid),
        sa.Column("product_id", uuid, nullable=False),
        sa.Column("raw_description", sa.Text(), nullable=False),
        sa.Column("normalized_description", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), server_default="1", nullable=False),
        sa.Column("match_method", sa.Text(), server_default="manual", nullable=False),
        sa.Column("confirmed_by_user_id", uuid),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="product_aliases_confidence_valid",
        ),
        sa.ForeignKeyConstraint(
            ["merchant_id", "household_id"],
            ["merchants.id", "merchants.household_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id", "household_id"],
            ["products.id", "products.household_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "household_id",
            "merchant_id",
            "normalized_description",
            name="product_aliases_identity_unique",
        ),
    )
    op.create_index(
        "product_aliases_household_description_idx",
        "product_aliases",
        ["household_id", "normalized_description"],
    )

    op.create_table(
        "product_enrichment_runs",
        sa.Column(
            "id", uuid, server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("household_id", uuid, nullable=False),
        sa.Column("receipt_item_id", uuid, nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("strategy", sa.Text(), server_default="local", nullable=False),
        sa.Column(
            "request_data", json, server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column(
            "result_data", json, server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("error_message", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'review')",
            name="product_enrichment_runs_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["receipt_item_id", "household_id"],
            ["receipt_items.id", "receipt_items.household_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "product_evidence",
        sa.Column(
            "id", uuid, server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("household_id", uuid, nullable=False),
        sa.Column("product_id", uuid, nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text()),
        sa.Column("external_id", sa.Text()),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column(
            "evidence_data", json, server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column(
            "retrieved_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="product_evidence_confidence_valid",
        ),
        sa.ForeignKeyConstraint(
            ["product_id", "household_id"],
            ["products.id", "products.household_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("product_evidence")
    op.drop_table("product_enrichment_runs")
    op.drop_index(
        "product_aliases_household_description_idx", table_name="product_aliases"
    )
    op.drop_table("product_aliases")
    op.drop_constraint(
        "receipt_items_product_match_confidence_valid", "receipt_items", type_="check"
    )
    op.drop_constraint(
        "receipt_items_product_match_status_valid", "receipt_items", type_="check"
    )
    op.drop_constraint(
        "receipt_items_product_scope_fk", "receipt_items", type_="foreignkey"
    )
    op.drop_constraint(
        "receipt_items_id_household_unique", "receipt_items", type_="unique"
    )
    for column in (
        "product_match_confidence",
        "product_match_method",
        "product_match_status",
        "product_id",
        "normalized_description",
    ):
        op.drop_column("receipt_items", column)
    op.drop_index("products_household_name_no_barcode_unique", table_name="products")
    op.drop_index("products_household_barcode_unique", table_name="products")
    op.drop_index("products_household_name_idx", table_name="products")
    op.drop_table("products")
