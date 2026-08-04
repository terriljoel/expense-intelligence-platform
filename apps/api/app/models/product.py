from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("id", "household_id", name="products_id_household_unique"),
        CheckConstraint("btrim(canonical_name) <> ''", name="products_name_not_blank"),
        CheckConstraint(
            "btrim(normalized_name) <> ''", name="products_normalized_name_not_blank"
        ),
        CheckConstraint(
            "barcode IS NULL OR barcode ~ '^[0-9]{8,14}$'",
            name="products_barcode_valid",
        ),
        Index("products_household_name_idx", "household_id", "normalized_name"),
        Index(
            "products_household_barcode_unique",
            "household_id",
            "barcode",
            unique=True,
            postgresql_where=text("barcode IS NOT NULL"),
        ),
        Index(
            "products_household_name_no_barcode_unique",
            "household_id",
            "normalized_name",
            unique=True,
            postgresql_where=text("barcode IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    household_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("households.id", ondelete="CASCADE"),
        nullable=False,
    )
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(Text)
    manufacturer: Mapped[str | None] = mapped_column(Text)
    family_name: Mapped[str | None] = mapped_column(Text)
    product_type: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'other'")
    )
    category: Mapped[str | None] = mapped_column(Text)
    barcode: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    nutrition: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    aliases: Mapped[list[ProductAlias]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


class ProductAlias(Base):
    __tablename__ = "product_aliases"
    __table_args__ = (
        ForeignKeyConstraint(
            ["product_id", "household_id"],
            ["products.id", "products.household_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["merchant_id", "household_id"],
            ["merchants.id", "merchants.household_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "household_id",
            "merchant_id",
            "normalized_description",
            name="product_aliases_identity_unique",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="product_aliases_confidence_valid",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    household_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    merchant_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    raw_description: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_description: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), nullable=False, server_default=text("1")
    )
    match_method: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'manual'")
    )
    confirmed_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    product: Mapped[Product] = relationship(back_populates="aliases")


class ProductEnrichmentRun(Base):
    __tablename__ = "product_enrichment_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["receipt_item_id", "household_id"],
            ["receipt_items.id", "receipt_items.household_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'review')",
            name="product_enrichment_runs_status_valid",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    household_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    receipt_item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pending'")
    )
    strategy: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'local'")
    )
    request_data: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    result_data: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProductEvidence(Base):
    __tablename__ = "product_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["product_id", "household_id"],
            ["products.id", "products.household_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="product_evidence_confidence_valid",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    household_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    evidence_data: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

