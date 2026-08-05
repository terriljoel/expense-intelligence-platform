from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["product_id", "household_id"],
            ["products.id", "products.household_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "id", "household_id", name="knowledge_documents_id_household_unique"
        ),
        UniqueConstraint(
            "household_id",
            "product_id",
            "content_sha256",
            name="knowledge_documents_content_unique",
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
    product_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content_text: Mapped[str | None] = mapped_column(Text)
    raw_object_key: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'text/markdown'")
    )
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class KnowledgeFact(Base):
    __tablename__ = "knowledge_facts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["document_id", "household_id"],
            ["knowledge_documents.id", "knowledge_documents.household_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["product_id", "household_id"],
            ["products.id", "products.household_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="knowledge_facts_confidence_valid",
        ),
        CheckConstraint(
            "confirmation_status IN ('suggested', 'confirmed', 'rejected')",
            name="knowledge_facts_status_valid",
        ),
        UniqueConstraint(
            "document_id", "fact_type", name="knowledge_facts_document_type_unique"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    household_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    document_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    fact_type: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    extraction_method: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    confirmation_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'suggested'")
    )
    confirmed_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
