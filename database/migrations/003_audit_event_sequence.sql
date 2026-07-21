BEGIN;

ALTER TABLE audit_events
    ADD COLUMN sequence_number BIGINT GENERATED ALWAYS AS IDENTITY;

ALTER TABLE audit_events
    ADD CONSTRAINT audit_events_sequence_number_key UNIQUE (sequence_number);

COMMIT;
