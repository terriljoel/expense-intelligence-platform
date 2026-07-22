BEGIN;

ALTER TABLE audit_events
    DROP CONSTRAINT audit_events_type_valid;

ALTER TABLE audit_events
    ADD CONSTRAINT audit_events_type_valid
    CHECK (
        event_type IN (
            'receipt_created',
            'receipt_updated',
            'item_added',
            'item_updated',
            'item_removed',
            'payment_added',
            'payment_updated',
            'payment_removed',
            'receipt_approved',
            'receipt_voided'
        )
    );

COMMIT;
