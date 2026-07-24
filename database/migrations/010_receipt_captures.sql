BEGIN;

CREATE TABLE receipt_captures (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id UUID NOT NULL,
    uploaded_by_user_id UUID NOT NULL,
    receipt_id UUID,
    original_filename TEXT,
    media_type VARCHAR(50) NOT NULL,
    byte_size BIGINT NOT NULL,
    image_sha256 VARCHAR(64) NOT NULL,
    image_object_key TEXT NOT NULL,
    ocr_status TEXT NOT NULL DEFAULT 'pending',
    ocr_provider TEXT,
    ocr_raw_text TEXT,
    ocr_error TEXT,
    suggested_merchant_name TEXT,
    suggested_purchase_date DATE,
    suggested_currency VARCHAR(3),
    suggested_total NUMERIC(14, 2),
    ocr_completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT receipt_captures_scope_unique UNIQUE (id, household_id),
    CONSTRAINT receipt_captures_household_hash_unique
        UNIQUE (household_id, image_sha256),
    CONSTRAINT receipt_captures_receipt_unique UNIQUE (receipt_id),
    CONSTRAINT receipt_captures_household_fk FOREIGN KEY (household_id)
        REFERENCES households (id),
    CONSTRAINT receipt_captures_member_fk
        FOREIGN KEY (household_id, uploaded_by_user_id)
        REFERENCES household_members (household_id, user_id),
    CONSTRAINT receipt_captures_receipt_scope_fk
        FOREIGN KEY (receipt_id, household_id)
        REFERENCES receipts (id, household_id),
    CONSTRAINT receipt_captures_hash_valid
        CHECK (image_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT receipt_captures_size_positive CHECK (byte_size > 0),
    CONSTRAINT receipt_captures_ocr_status_valid
        CHECK (ocr_status IN ('pending', 'processing', 'succeeded', 'failed')),
    CONSTRAINT receipt_captures_currency_valid
        CHECK (suggested_currency IS NULL OR suggested_currency ~ '^[A-Z]{3}$'),
    CONSTRAINT receipt_captures_total_nonnegative
        CHECK (suggested_total IS NULL OR suggested_total >= 0)
);

CREATE INDEX receipt_captures_household_created_idx
    ON receipt_captures (household_id, created_at DESC);

COMMIT;
