# Receipt correction and voiding API

Use these endpoints instead of editing receipt rows directly in PostgreSQL.
Every successful change to a draft receipt creates an immutable audit event in
the same transaction.

## Lifecycle rules

```text
draft ──approve──> approved ──void──> voided
  │                                  ▲
  └──────────────void────────────────┘
```

- Receipt headers, items and payments can be changed only in `draft` status.
- Approved receipts cannot be edited, but they can be voided.
- Voided receipts cannot be edited, approved or voided again.
- Removing an item or payment does not erase its audit history.
- Reconciliation is recalculated from the current rows whenever it is read.

## Update the receipt header

```text
PATCH /receipts/{receipt_id}
```

Example:

```json
{
  "merchant_id": "MERCHANT_ID",
  "purchase_date": "2026-07-23",
  "currency": "EUR",
  "stated_total": "12.00",
  "notes": "Corrected receipt"
}
```

`PATCH` changes only supplied fields. Send `merchant_id: null` to remove the
merchant and `notes: null` to clear notes. Purchase date, currency and stated
total cannot be null.

Audit event: `receipt_updated`, containing the old and new value of each changed
field.

## Update an item

First obtain item IDs:

```text
GET /receipts/{receipt_id}/items
```

Then update one:

```text
PATCH /receipts/{receipt_id}/items/{item_id}
```

```json
{
  "description": "Corrected groceries",
  "line_total": "12.00"
}
```

The API validates the final line type and sign. For example, a discount cannot
have a positive total. Changing `position` cannot duplicate another position on
the same receipt.

Audit event: `item_updated` with `item_id` and field-level old/new values.

## Remove an item

```text
DELETE /receipts/{receipt_id}/items/{item_id}
```

Expected status: `204 No Content`. The item row is removed, while an
`item_removed` event preserves its ID, position, type, description and amount.

## Update a payment

First obtain payment IDs:

```text
GET /receipts/{receipt_id}/payments
```

Then update the selected payment:

```text
PATCH /receipts/{receipt_id}/payments/{payment_id}
```

Correct only the amount:

```json
{
  "amount": "12.00"
}
```

Change both method and amount:

```json
{
  "payment_method_id": "PAYMENT_METHOD_ID",
  "amount": "12.00"
}
```

The new method must be active and owned by the current user in the current
household. The same method cannot appear twice for that user's payments on one
receipt.

Audit event: `payment_updated` with `payment_id` and field-level old/new values.

## Remove a payment

```text
DELETE /receipts/{receipt_id}/payments/{payment_id}
```

Expected status: `204 No Content`. A `payment_removed` event preserves the
payment ID, method ID and amount.

## Recheck reconciliation

After every correction, use:

```text
GET /receipts/{receipt_id}/reconciliation
```

Approval requires:

```text
item_count > 0
payment_count > 0
stated_total = item_total = payment_total
is_reconciled = true
```

Then approve:

```text
POST /receipts/{receipt_id}/approve
```

## Void a receipt

Void a draft or approved receipt:

```text
POST /receipts/{receipt_id}/void
```

```json
{
  "reason": "Duplicate receipt"
}
```

The reason is optional but recommended. The response contains `status: voided`
and a `voided_at` timestamp. The `receipt_voided` event records the previous
status and reason.

Voiding preserves the receipt, items, payments and complete audit trail. This is
safer than deletion for financial records.

## Read the audit history

```text
GET /receipts/{receipt_id}/audit-events
```

Supported events are:

```text
receipt_created
receipt_updated
item_added
item_updated
item_removed
payment_added
payment_updated
payment_removed
receipt_approved
receipt_voided
```

Audit rows are ordered by `sequence_number` and PostgreSQL rejects `UPDATE` and
`DELETE` against them.

## Common responses

| Status | Meaning |
|---:|---|
| `200 OK` | Update, approval, void or read succeeded. |
| `204 No Content` | Item or payment removal succeeded. |
| `404 Not Found` | Receipt, child record, merchant or active method is missing or outside the permitted scope. |
| `409 Conflict` | Receipt is not editable, a position/method conflicts, reconciliation fails, or voiding is invalid. |
| `422 Unprocessable Entity` | Request format, amount, currency, nullability or line sign is invalid. |

## Example: correct a payment from 1.00 to 12.00

```text
PATCH /receipts/c78377c0-f5c2-4682-94b6-2bc86eccb09b/payments/3512256b-ec0d-4d7c-a9fc-e76edd3e617d
```

```json
{
  "amount": "12.00"
}
```

Unlike a direct SQL update, this creates `payment_updated` and preserves both
the original `1.00` and corrected `12.00` values in the audit trail.
