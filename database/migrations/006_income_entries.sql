BEGIN;

CREATE TABLE income_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id UUID NOT NULL,
    received_by_user_id UUID NOT NULL,
    destination_payment_method_id UUID,
    source TEXT NOT NULL,
    income_type TEXT NOT NULL DEFAULT 'other',
    received_date DATE NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'EUR',
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT income_entries_scope_unique UNIQUE (id, household_id),
    CONSTRAINT income_entries_household_fk
        FOREIGN KEY (household_id) REFERENCES households (id),
    CONSTRAINT income_entries_member_fk
        FOREIGN KEY (household_id, received_by_user_id)
        REFERENCES household_members (household_id, user_id),
    CONSTRAINT income_entries_destination_method_scope_fk
        FOREIGN KEY (
            destination_payment_method_id,
            household_id,
            received_by_user_id
        ) REFERENCES payment_methods (id, household_id, user_id),
    CONSTRAINT income_entries_source_not_blank CHECK (btrim(source) <> ''),
    CONSTRAINT income_entries_type_valid CHECK (
        income_type IN (
            'salary', 'freelance', 'interest', 'gift', 'refund', 'other'
        )
    ),
    CONSTRAINT income_entries_amount_positive CHECK (amount > 0),
    CONSTRAINT income_entries_currency_valid CHECK (
        currency ~ '^[A-Z]{3}$'
    )
);

CREATE INDEX income_entries_household_received_date_idx
    ON income_entries (household_id, received_date DESC);

COMMIT;
