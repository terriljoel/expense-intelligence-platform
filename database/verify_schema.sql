\set ON_ERROR_STOP on

BEGIN;

INSERT INTO users (auth_subject, email, display_name)
VALUES ('local-dev-terril', 'terril@example.test', 'Terril')
RETURNING id AS test_user_id \gset

INSERT INTO households (name, default_currency)
VALUES ('Personal Household', 'EUR')
RETURNING id AS test_household_id \gset

INSERT INTO household_members (household_id, user_id, role)
VALUES (:'test_household_id', :'test_user_id', 'owner');

INSERT INTO merchants (household_id, name, normalized_name)
VALUES (:'test_household_id', 'REWE', 'rewe')
RETURNING id AS test_merchant_id \gset

INSERT INTO payment_methods (
    household_id,
    user_id,
    name,
    method_type
)
VALUES (
    :'test_household_id',
    :'test_user_id',
    'Cash',
    'cash'
)
RETURNING id AS test_payment_method_id \gset

INSERT INTO receipts (
    household_id,
    merchant_id,
    created_by_user_id,
    purchase_date,
    currency,
    stated_total,
    status,
    source
)
VALUES (
    :'test_household_id',
    :'test_merchant_id',
    :'test_user_id',
    CURRENT_DATE,
    'EUR',
    8.50,
    'draft',
    'manual'
)
RETURNING id AS test_receipt_id \gset

INSERT INTO receipt_items (
    household_id,
    receipt_id,
    position,
    line_type,
    description,
    quantity,
    unit_price,
    line_total
)
VALUES
    (:'test_household_id', :'test_receipt_id', 1, 'product', 'Milk',       1, 2.00,  2.00),
    (:'test_household_id', :'test_receipt_id', 2, 'product', 'Bread',      1, 3.00,  3.00),
    (:'test_household_id', :'test_receipt_id', 3, 'deposit', 'Pfand',      1, 0.50,  0.50),
    (:'test_household_id', :'test_receipt_id', 4, 'product', 'Vegetables', 1, 4.00,  4.00),
    (:'test_household_id', :'test_receipt_id', 5, 'discount', 'Discount', NULL, NULL, -1.00);

INSERT INTO receipt_payments (
    user_id,
    payment_method_id,
    household_id,
    receipt_id,
    amount
)
VALUES (
    :'test_user_id',
    :'test_payment_method_id',
    :'test_household_id',
    :'test_receipt_id',
    8.50
);

SELECT
    CASE WHEN is_reconciled THEN 'true' ELSE 'false' END
        AS reconciliation_result
FROM receipt_reconciliation
WHERE receipt_id = :'test_receipt_id'
\gset

\if :reconciliation_result
\echo 'Receipt reconciliation check passed.'
\else
\echo 'Receipt reconciliation check failed.'
\quit 1
\endif

SELECT
    receipt_id,
    stated_total,
    item_total,
    payment_total,
    is_reconciled
FROM receipt_reconciliation
WHERE receipt_id = :'test_receipt_id';

ROLLBACK;
