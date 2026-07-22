\set ON_ERROR_STOP on

BEGIN;

INSERT INTO users (auth_subject, email, display_name)
VALUES ('schema-verify-user', 'schema-verify@example.test', 'Schema Verify')
RETURNING id AS test_user_id \gset

INSERT INTO households (name, default_currency)
VALUES ('Personal Household', 'EUR')
RETURNING id AS test_household_id \gset

INSERT INTO household_members (household_id, user_id, role)
VALUES (:'test_household_id', :'test_user_id', 'owner');

SELECT
    CASE WHEN is_active THEN 'true' ELSE 'false' END
        AS active_membership_result
FROM household_members
WHERE household_id = :'test_household_id'
  AND user_id = :'test_user_id'
\gset

\if :active_membership_result
\echo 'Active household membership check passed.'
\else
\echo 'Active household membership check failed.'
\quit 1
\endif

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

INSERT INTO user_credentials (user_id, password_hash)
VALUES (:'test_user_id', '$argon2id$schema-verification-placeholder');

INSERT INTO auth_sessions (
    household_id,
    user_id,
    token_hash,
    expires_at
)
VALUES (
    :'test_household_id',
    :'test_user_id',
    repeat('a', 64),
    now() + interval '1 hour'
)
RETURNING id AS test_auth_session_id \gset

INSERT INTO household_invitations (
    household_id,
    email,
    role,
    token_hash,
    invited_by_user_id,
    expires_at
)
VALUES (
    :'test_household_id',
    'invited-schema-verify@example.test',
    'member',
    repeat('b', 64),
    :'test_user_id',
    now() + interval '7 days'
)
RETURNING id AS test_invitation_id \gset

INSERT INTO income_entries (
    household_id,
    received_by_user_id,
    destination_payment_method_id,
    source,
    income_type,
    received_date,
    amount,
    currency
)
VALUES (
    :'test_household_id',
    :'test_user_id',
    :'test_payment_method_id',
    'Schema Verification Employer',
    'salary',
    CURRENT_DATE,
    2500.00,
    'EUR'
)
RETURNING id AS test_income_id \gset

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
    CASE WHEN role = 'member'
              AND accepted_at IS NULL
              AND expires_at > now()
        THEN 'true' ELSE 'false' END AS invitation_result
FROM household_invitations
WHERE id = :'test_invitation_id'
\gset

\if :invitation_result
\echo 'Household invitation check passed.'
\else
\echo 'Household invitation check failed.'
\quit 1
\endif

SELECT
    CASE WHEN expires_at > now() THEN 'true' ELSE 'false' END
        AS auth_session_result
FROM auth_sessions
WHERE id = :'test_auth_session_id'
\gset

\if :auth_session_result
\echo 'Authentication session check passed.'
\else
\echo 'Authentication session check failed.'
\quit 1
\endif

SELECT
    CASE WHEN amount = 2500.00 AND income_type = 'salary'
        THEN 'true' ELSE 'false' END AS income_result
FROM income_entries
WHERE id = :'test_income_id'
\gset

\if :income_result
\echo 'Income entry check passed.'
\else
\echo 'Income entry check failed.'
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
