# Manual API vertical slice

Use this after completing
[`DOCKER_POSTGRES_FASTAPI_GUIDE.md`](./DOCKER_POSTGRES_FASTAPI_GUIDE.md).

A vertical slice exercises all layers of one feature:

```text
Swagger → FastAPI → Pydantic → service → SQLAlchemy → PostgreSQL → response
```

Keep Docker PostgreSQL and FastAPI running, then open Swagger:

<http://127.0.0.1:8000/docs>

For each endpoint, expand it, select **Try it out**, enter the values, and
select **Execute**. `POST` creates or changes data, `PATCH` partially updates
data, and `GET` reads data.

## 1. Check the database connection

```text
GET /health/ready
```

No body is required. `200 OK` confirms FastAPI can query PostgreSQL.

## 2. Create a merchant

```text
POST /merchants
```

```json
{
  "name": "Demo Market"
}
```

This creates a household-scoped merchant. Copy its response `id`; call it
`MERCHANT_ID`. Expected status: `201 Created`.

If the same normalized name already exists, `409 Conflict` prevents a
duplicate. Use its existing ID or choose another name.

## 3. Create a payment method

```text
POST /payment-methods
```

```json
{
  "name": "My Demo Visa",
  "method_type": "credit_card",
  "provider": "Demo Bank",
  "last_four": "1234"
}
```

| Field | Meaning |
|---|---|
| `name` | User-facing selection name. |
| `method_type` | Cash, card, transfer, wallet, voucher or another supported type. |
| `provider` | Optional bank, wallet or card provider. |
| `last_four` | Optional final four digits; exactly four numeric characters. |

The API automatically assigns the current user, current household and
`is_active=true`. Never submit a full card number, CVV, PIN or banking password.

Copy the response `id`; call it `PAYMENT_METHOD_ID`. Expected status: `201
Created`. Creating an equivalent active method returns `409 Conflict`.

Confirm it is available:

```text
GET /payment-methods
GET /payment-methods/{payment_method_id}
```

Replace `{payment_method_id}` with the real UUID. Both reads return `200 OK`.

## 4. Create a draft receipt

```text
POST /receipts
```

Replace `MERCHANT_ID`:

```json
{
  "merchant_id": "MERCHANT_ID",
  "purchase_date": "2026-07-22",
  "currency": "EUR",
  "stated_total": "12.50",
  "notes": "Manual vertical-slice test"
}
```

| Field | Meaning |
|---|---|
| `merchant_id` | Merchant connected to the receipt. |
| `purchase_date` | Date in `YYYY-MM-DD` format. |
| `currency` | Three-letter currency code. |
| `stated_total` | Printed total; a string preserves exact decimal money. |
| `notes` | Optional note. |

This creates a `draft` receipt and `receipt_created` audit event in one
transaction. Copy the response `id`; call it `RECEIPT_ID`. Expected status:
`201 Created`.

## 5. Add a receipt item

```text
POST /receipts/{receipt_id}/items
```

Replace the path value with `RECEIPT_ID`:

```json
{
  "position": 1,
  "line_type": "product",
  "description": "Demo groceries",
  "quantity": 1,
  "unit_price": "12.50",
  "line_total": "12.50"
}
```

| Field | Meaning |
|---|---|
| `position` | Line order, unique inside the receipt. |
| `line_type` | Product, deposit, discount, fee, tax or adjustment. |
| `description` | Clean item description. |
| `quantity` | Optional positive number of units. |
| `unit_price` | Optional non-negative price per unit. |
| `line_total` | Amount this line contributes to the receipt. |

This creates a receipt item and `item_added` audit event. Expected status: `201
Created`.

## 6. Add the receipt payment

```text
POST /receipts/{receipt_id}/payments
```

Use `RECEIPT_ID` in the path and the method created in step 3:

```json
{
  "payment_method_id": "PAYMENT_METHOD_ID",
  "amount": "12.50"
}
```

The service verifies that the method is active and belongs to the current user
and household. It creates the payment and `payment_added` event together.
Expected status: `201 Created`.

## 7. Reconcile the totals

```text
GET /receipts/{receipt_id}/reconciliation
```

Expected result:

```json
{
  "receipt_id": "RECEIPT_ID",
  "stated_total": "12.50",
  "item_total": "12.50",
  "payment_total": "12.50",
  "item_difference": "0.00",
  "payment_difference": "0.00",
  "item_count": 1,
  "payment_count": 1,
  "is_reconciled": true
}
```

Reconciliation requires:

```text
stated total = item total = payment total
```

Do not approve while `is_reconciled` is false.

## 8. Approve the receipt

```text
POST /receipts/{receipt_id}/approve
```

No body is required. The service locks the receipt, confirms it is a draft,
requires at least one item and payment, checks both totals, sets `approved_at`,
adds `receipt_approved`, and commits everything together.

Expected status: `200 OK`, with `status: "approved"` and a non-null
`approved_at`. Approved receipts reject new items and payments.

## 9. Read the audit trail

```text
GET /receipts/{receipt_id}/audit-events
```

Expected event order:

```text
receipt_created
item_added
payment_added
receipt_approved
```

Sequence numbers may start above 1 because they are global. PostgreSQL rejects
updates and deletes on audit events.

## 10. Read all receipt parts

```text
GET /receipts/{receipt_id}
GET /receipts/{receipt_id}/items
GET /receipts/{receipt_id}/payments
GET /receipts?limit=50&offset=0
```

| URL part | Meaning |
|---|---|
| `{receipt_id}` | Replace with the real receipt UUID. |
| `?` | Start URL query options. |
| `limit=50` | Return at most 50 receipts. |
| `&` | Separate query options. |
| `offset=0` | Skip zero rows; use 50 for the next page. |

## 11. Update and deactivate the payment method

Update safe display metadata:

```text
PATCH /payment-methods/{payment_method_id}
```

```json
{
  "name": "Updated Demo Visa",
  "provider": "Updated Demo Bank"
}
```

`PATCH` changes only supplied fields. Ownership cannot be changed. Expected
status: `200 OK`.

Deactivate the method:

```text
POST /payment-methods/{payment_method_id}/deactivate
```

No body is required. Historical receipt payments remain, but the method cannot
pay new receipts. The response contains `is_active: false`.

The normal list hides inactive methods:

```text
GET /payment-methods
```

Include them for account management:

```text
GET /payment-methods?include_inactive=true
```

## 12. Verify the records in PostgreSQL

Open `psql` as explained in the main guide and replace each placeholder:

```sql
SELECT id, name, method_type, provider, last_four, is_active
FROM payment_methods
WHERE id = 'PAYMENT_METHOD_ID';

SELECT id, purchase_date, stated_total, status
FROM receipts
WHERE id = 'RECEIPT_ID';

SELECT position, description, line_total
FROM receipt_items
WHERE receipt_id = 'RECEIPT_ID'
ORDER BY position;

SELECT payment_method_id, amount
FROM receipt_payments
WHERE receipt_id = 'RECEIPT_ID';

SELECT stated_total, item_total, payment_total, is_reconciled
FROM receipt_reconciliation
WHERE receipt_id = 'RECEIPT_ID';

SELECT sequence_number, event_type, event_data, created_at
FROM audit_events
WHERE receipt_id = 'RECEIPT_ID'
ORDER BY sequence_number;
```

`WHERE` filters the query to one record. Seeing the same values proves the
Swagger requests crossed the complete vertical slice and reached PostgreSQL.
