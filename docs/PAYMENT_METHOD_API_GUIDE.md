# Payment-method API workflow

Use this workflow in Swagger at <http://127.0.0.1:8000/docs> before adding a
payment to a receipt.

## Create

```text
POST /payment-methods
```

```json
{
  "name": "My Visa",
  "method_type": "credit_card",
  "provider": "Example Bank",
  "last_four": "1234"
}
```

The server assigns the current user, current household and `is_active=true`.
Expected status: `201 Created`. Copy the returned `id` for the receipt-payment
request. An equivalent active method returns `409 Conflict`.

Supported `method_type` values:

```text
cash
debit_card
credit_card
bank_transfer
direct_debit
mobile_wallet
voucher
other
```

Store only safe metadata. Never submit a full card number, CVV, PIN or banking
password.

## Read

```text
GET /payment-methods
GET /payment-methods/{payment_method_id}
```

The list returns active methods owned by the current user in the current
household. Replace `{payment_method_id}` with the returned UUID.

Include inactive methods:

```text
GET /payment-methods?include_inactive=true
```

`?` starts URL query options. `include_inactive=true` disables the default
active-only filter.

## Update

```text
PATCH /payment-methods/{payment_method_id}
```

```json
{
  "name": "Daily Visa",
  "provider": "Updated Bank"
}
```

`PATCH` changes only fields included in the request. The method cannot be moved
to another user or household. An empty body returns `422 Unprocessable Entity`.

## Use on a receipt

```text
POST /receipts/{receipt_id}/payments
```

```json
{
  "payment_method_id": "PAYMENT_METHOD_ID",
  "amount": "12.50"
}
```

The API verifies that the method is active and belongs to the current user and
household before storing the payment.

## Deactivate

```text
POST /payment-methods/{payment_method_id}/deactivate
```

No body is needed. Deactivation preserves historical receipt payments but
blocks the method from new payments. It also disappears from the default list;
use `include_inactive=true` to see it.

## PostgreSQL verification

```sql
SELECT id, user_id, name, method_type, provider, last_four, is_active
FROM payment_methods
ORDER BY created_at;
```

The database prevents two equivalent active methods for the same user and
household. It also enforces valid method types and exactly four numeric
characters when `last_four` is supplied.
