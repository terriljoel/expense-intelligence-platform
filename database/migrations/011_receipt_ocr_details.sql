BEGIN;

ALTER TABLE receipt_captures
    ADD COLUMN ocr_result JSONB,
    ADD COLUMN suggested_merchant_address TEXT,
    ADD COLUMN suggested_merchant_phone TEXT,
    ADD COLUMN suggested_transaction_time TIME,
    ADD COLUMN suggested_subtotal NUMERIC(14, 2),
    ADD COLUMN suggested_tax NUMERIC(14, 2),
    ADD COLUMN suggested_tip NUMERIC(14, 2);

ALTER TABLE receipts
    ADD COLUMN purchase_time TIME,
    ADD COLUMN merchant_address TEXT,
    ADD COLUMN merchant_phone TEXT,
    ADD COLUMN subtotal NUMERIC(14, 2),
    ADD COLUMN tax_amount NUMERIC(14, 2),
    ADD COLUMN tip_amount NUMERIC(14, 2);

COMMIT;
