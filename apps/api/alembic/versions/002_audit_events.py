"""Add append-only receipt audit events.

Revision ID: 002_audit_events
Revises: 001_initial_schema
Create Date: 2026-07-22
"""

from collections.abc import Sequence

from alembic import op


revision: str = "002_audit_events"
down_revision: str | None = "001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE audit_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            household_id UUID NOT NULL,
            actor_user_id UUID NOT NULL,
            receipt_id UUID NOT NULL,
            event_type TEXT NOT NULL,
            event_data JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT audit_events_actor_membership_fk
                FOREIGN KEY (household_id, actor_user_id)
                REFERENCES household_members (household_id, user_id),
            CONSTRAINT audit_events_receipt_scope_fk
                FOREIGN KEY (receipt_id, household_id)
                REFERENCES receipts (id, household_id),
            CONSTRAINT audit_events_type_valid CHECK (
                event_type IN (
                    'receipt_created', 'item_added',
                    'payment_added', 'receipt_approved'
                )
            )
        );
        CREATE INDEX audit_events_receipt_created_idx
            ON audit_events (receipt_id, created_at DESC);
        CREATE INDEX audit_events_household_created_idx
            ON audit_events (household_id, created_at DESC);
        CREATE FUNCTION prevent_audit_event_mutation()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events is append-only';
        END;
        $$;
        CREATE TRIGGER audit_events_prevent_update
        BEFORE UPDATE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_event_mutation();
        CREATE TRIGGER audit_events_prevent_delete
        BEFORE DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_event_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER audit_events_prevent_delete ON audit_events")
    op.execute("DROP TRIGGER audit_events_prevent_update ON audit_events")
    op.execute("DROP FUNCTION prevent_audit_event_mutation()")
    op.drop_table("audit_events")
