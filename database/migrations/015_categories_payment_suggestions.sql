BEGIN;

ALTER TABLE receipts ADD COLUMN category text NOT NULL DEFAULT 'other';
ALTER TABLE receipts ADD CONSTRAINT receipts_category_valid CHECK (
    category IN ('groceries', 'rent', 'health_insurance', 'transport',
    'university_fees', 'utilities', 'subscriptions', 'dining', 'shopping',
    'travel', 'other')
);
ALTER TABLE income_entries ADD COLUMN category text NOT NULL DEFAULT 'other';
ALTER TABLE income_entries ADD CONSTRAINT income_entries_category_valid CHECK (
    category IN ('salary_payslip', 'freelance', 'interest', 'gift', 'refund',
    'benefits', 'other')
);
ALTER TABLE receipt_captures
    ADD COLUMN suggested_payment_type text,
    ADD COLUMN suggested_payment_provider text,
    ADD COLUMN suggested_payment_last_four varchar(4),
    ADD COLUMN suggested_payment_method_id uuid,
    ADD COLUMN suggested_payment_reason text,
    ADD CONSTRAINT receipt_captures_suggested_method_scope_fk FOREIGN KEY
        (suggested_payment_method_id, household_id, uploaded_by_user_id)
        REFERENCES payment_methods (id, household_id, user_id);

COMMIT;
