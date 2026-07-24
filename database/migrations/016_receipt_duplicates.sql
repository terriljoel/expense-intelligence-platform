BEGIN;

ALTER TABLE receipts
    ADD COLUMN receipt_number text,
    ADD COLUMN normalized_receipt_number text;
CREATE UNIQUE INDEX receipts_number_identity_unique ON receipts
    (household_id, merchant_id, purchase_date, normalized_receipt_number)
    WHERE normalized_receipt_number IS NOT NULL AND status <> 'voided';
ALTER TABLE receipt_captures
    ADD COLUMN suggested_receipt_number text,
    ADD COLUMN possible_duplicate_receipt_id uuid,
    ADD COLUMN duplicate_match_level varchar(20),
    ADD COLUMN duplicate_reason text,
    ADD CONSTRAINT receipt_captures_duplicate_level_valid CHECK (
        duplicate_match_level IS NULL OR duplicate_match_level IN ('possible', 'strong')
    );

COMMIT;
