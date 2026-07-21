BEGIN;

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
    CONSTRAINT audit_events_type_valid
        CHECK (
            event_type IN (
                'receipt_created',
                'item_added',
                'payment_added',
                'receipt_approved'
            )
        )
);

CREATE INDEX audit_events_receipt_created_idx
    ON audit_events (receipt_id, created_at DESC);

CREATE INDEX audit_events_household_created_idx
    ON audit_events (household_id, created_at DESC);

CREATE FUNCTION prevent_audit_event_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
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

COMMIT;
