BEGIN;

ALTER TABLE receipt_captures
    ADD COLUMN suggested_items JSONB;

COMMIT;
