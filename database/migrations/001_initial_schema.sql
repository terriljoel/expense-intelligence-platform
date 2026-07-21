BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_subject TEXT NOT NULL UNIQUE,
    email TEXT UNIQUE,
    display_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT users_auth_subject_not_blank
        CHECK (btrim(auth_subject) <> ''),
    CONSTRAINT users_display_name_not_blank
        CHECK (btrim(display_name) <> '')
);

CREATE TABLE households (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    default_currency VARCHAR(3) NOT NULL DEFAULT 'EUR',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT households_name_not_blank
        CHECK (btrim(name) <> ''),
    CONSTRAINT households_currency_valid
        CHECK (default_currency ~ '^[A-Z]{3}$')
);

CREATE TABLE household_members (
    household_id UUID NOT NULL,
    user_id UUID NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (household_id, user_id),

    CONSTRAINT household_members_household_fk
        FOREIGN KEY (household_id)
        REFERENCES households (id),
    CONSTRAINT household_members_user_fk
        FOREIGN KEY (user_id)
        REFERENCES users (id),
    CONSTRAINT household_members_role_valid
        CHECK (role IN ('owner', 'admin', 'member'))
);

CREATE TABLE merchants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id UUID NOT NULL,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT merchants_id_household_unique
        UNIQUE (id, household_id),
    CONSTRAINT merchants_normalized_name_unique
        UNIQUE (household_id, normalized_name),
    CONSTRAINT merchants_household_fk
        FOREIGN KEY (household_id)
        REFERENCES households (id),
    CONSTRAINT merchants_name_not_blank
        CHECK (btrim(name) <> ''),
    CONSTRAINT merchants_normalized_name_not_blank
        CHECK (btrim(normalized_name) <> '')
);

CREATE TABLE payment_methods (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id UUID NOT NULL,
    user_id UUID NOT NULL,
    name TEXT NOT NULL,
    method_type TEXT NOT NULL,
    provider TEXT,
    last_four VARCHAR(4),
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT payment_methods_scope_unique
        UNIQUE (id, household_id, user_id),
    CONSTRAINT payment_methods_member_fk
        FOREIGN KEY (household_id, user_id)
        REFERENCES household_members (household_id, user_id),
    CONSTRAINT payment_methods_name_not_blank
        CHECK (btrim(name) <> ''),
    CONSTRAINT payment_methods_type_valid
        CHECK (
            method_type IN (
                'cash',
                'debit_card',
                'credit_card',
                'bank_transfer',
                'direct_debit',
                'mobile_wallet',
                'voucher',
                'other'
            )
        ),
    CONSTRAINT payment_methods_last_four_valid
        CHECK (last_four IS NULL OR last_four ~ '^[0-9]{4}$')
);

CREATE TABLE receipts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id UUID NOT NULL,
    merchant_id UUID,
    created_by_user_id UUID NOT NULL,
    purchase_date DATE NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'EUR',
    stated_total NUMERIC(14, 2) NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    source TEXT NOT NULL DEFAULT 'manual',
    image_object_key TEXT,
    image_sha256 VARCHAR(64),
    notes TEXT,
    approved_at TIMESTAMPTZ,
    voided_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT receipts_id_household_unique
        UNIQUE (id, household_id),
    CONSTRAINT receipts_household_fk
        FOREIGN KEY (household_id)
        REFERENCES households (id),
    CONSTRAINT receipts_creator_membership_fk
        FOREIGN KEY (household_id, created_by_user_id)
        REFERENCES household_members (household_id, user_id),
    CONSTRAINT receipts_merchant_scope_fk
        FOREIGN KEY (merchant_id, household_id)
        REFERENCES merchants (id, household_id),
    CONSTRAINT receipts_currency_valid
        CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT receipts_total_nonnegative
        CHECK (stated_total >= 0),
    CONSTRAINT receipts_status_valid
        CHECK (
            status IN (
                'draft',
                'pending_review',
                'reconciliation_failed',
                'approved',
                'voided'
            )
        ),
    CONSTRAINT receipts_source_valid
        CHECK (source IN ('manual', 'image', 'import')),
    CONSTRAINT receipts_image_hash_valid
        CHECK (image_sha256 IS NULL OR image_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT receipts_approved_state_valid
        CHECK (status <> 'approved' OR approved_at IS NOT NULL),
    CONSTRAINT receipts_voided_state_valid
        CHECK (status <> 'voided' OR voided_at IS NOT NULL)
);

CREATE UNIQUE INDEX receipts_active_image_hash_unique
    ON receipts (household_id, image_sha256)
    WHERE image_sha256 IS NOT NULL AND status <> 'voided';

CREATE INDEX receipts_household_purchase_date_idx
    ON receipts (household_id, purchase_date DESC);

CREATE INDEX receipts_merchant_idx
    ON receipts (household_id, merchant_id);

CREATE TABLE receipt_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id UUID NOT NULL,
    receipt_id UUID NOT NULL,
    position INTEGER NOT NULL,
    line_type TEXT NOT NULL DEFAULT 'product',
    raw_description TEXT,
    description TEXT NOT NULL,
    raw_quantity_text TEXT,
    quantity NUMERIC(12, 3),
    unit_price NUMERIC(14, 4),
    line_total NUMERIC(14, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT receipt_items_position_unique
        UNIQUE (receipt_id, position),
    CONSTRAINT receipt_items_receipt_scope_fk
        FOREIGN KEY (receipt_id, household_id)
        REFERENCES receipts (id, household_id)
        ON DELETE CASCADE,
    CONSTRAINT receipt_items_position_positive
        CHECK (position > 0),
    CONSTRAINT receipt_items_description_not_blank
        CHECK (btrim(description) <> ''),
    CONSTRAINT receipt_items_quantity_positive
        CHECK (quantity IS NULL OR quantity > 0),
    CONSTRAINT receipt_items_unit_price_nonnegative
        CHECK (unit_price IS NULL OR unit_price >= 0),
    CONSTRAINT receipt_items_line_type_valid
        CHECK (
            line_type IN (
                'product',
                'deposit',
                'discount',
                'fee',
                'tax',
                'adjustment'
            )
        ),
    CONSTRAINT receipt_items_amount_sign_valid
        CHECK (
            line_type = 'adjustment'
            OR (line_type = 'discount' AND line_total <= 0)
            OR (
                line_type IN ('product', 'deposit', 'fee', 'tax')
                AND line_total >= 0
            )
        )
);

CREATE INDEX receipt_items_receipt_position_idx
    ON receipt_items (receipt_id, position);

CREATE TABLE receipt_payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    payment_method_id UUID,
    household_id UUID NOT NULL,
    receipt_id UUID NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT receipt_payments_method_unique
        UNIQUE (receipt_id, user_id, payment_method_id),
    CONSTRAINT receipt_payments_receipt_scope_fk
        FOREIGN KEY (receipt_id, household_id)
        REFERENCES receipts (id, household_id)
        ON DELETE CASCADE,
    CONSTRAINT receipt_payments_member_fk
        FOREIGN KEY (household_id, user_id)
        REFERENCES household_members (household_id, user_id),
    CONSTRAINT receipt_payments_method_scope_fk
        FOREIGN KEY (payment_method_id, household_id, user_id)
        REFERENCES payment_methods (id, household_id, user_id),
    CONSTRAINT receipt_payments_amount_positive
        CHECK (amount > 0)
);

CREATE INDEX receipt_payments_receipt_idx
    ON receipt_payments (receipt_id);

CREATE VIEW receipt_reconciliation AS
WITH item_totals AS (
    SELECT
        receipt_id,
        SUM(line_total)::NUMERIC(14, 2) AS item_total
    FROM receipt_items
    GROUP BY receipt_id
),
payment_totals AS (
    SELECT
        receipt_id,
        SUM(amount)::NUMERIC(14, 2) AS payment_total
    FROM receipt_payments
    GROUP BY receipt_id
)
SELECT
    receipt.id AS receipt_id,
    receipt.household_id,
    receipt.stated_total,
    COALESCE(item_totals.item_total, 0)::NUMERIC(14, 2) AS item_total,
    COALESCE(payment_totals.payment_total, 0)::NUMERIC(14, 2) AS payment_total,
    (
        receipt.stated_total - COALESCE(item_totals.item_total, 0)
    )::NUMERIC(14, 2) AS item_difference,
    (
        receipt.stated_total - COALESCE(payment_totals.payment_total, 0)
    )::NUMERIC(14, 2) AS payment_difference,
    receipt.stated_total = COALESCE(item_totals.item_total, 0)
        AND receipt.stated_total = COALESCE(payment_totals.payment_total, 0)
        AS is_reconciled
FROM receipts AS receipt
LEFT JOIN item_totals ON item_totals.receipt_id = receipt.id
LEFT JOIN payment_totals ON payment_totals.receipt_id = receipt.id;

CREATE FUNCTION set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER users_set_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER households_set_updated_at
BEFORE UPDATE ON households
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER merchants_set_updated_at
BEFORE UPDATE ON merchants
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER payment_methods_set_updated_at
BEFORE UPDATE ON payment_methods
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER receipts_set_updated_at
BEFORE UPDATE ON receipts
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER receipt_items_set_updated_at
BEFORE UPDATE ON receipt_items
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMIT;
