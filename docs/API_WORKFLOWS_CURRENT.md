# Current API and UI workflows

This guide applies through migration `016_receipt_duplicates`.

Swagger: <http://127.0.0.1:8000/docs>

## Manual receipt workflow

1. Create or reuse a branch-aware merchant:

```json
POST /merchants
{
  "name": "Demo Market",
  "address": "Example Street 1, 38100 Braunschweig"
}
```

2. Create or reuse a user-owned payment method:

```json
POST /payment-methods
{
  "name": "Personal Visa",
  "method_type": "credit_card",
  "provider": "Visa",
  "last_four": "1234"
}
```

3. Create the draft:

```json
POST /receipts
{
  "merchant_id": "MERCHANT_ID",
  "payment_method_id": "PAYMENT_METHOD_ID",
  "category": "groceries",
  "receipt_number": "DEMO-2026-001",
  "purchase_date": "2026-07-23",
  "currency": "EUR",
  "stated_total": "12.50",
  "notes": "Manual test"
}
```

4. Add items, reconcile and approve:

```text
POST /receipts/{receipt_id}/items
POST /receipts/{receipt_id}/payments       # if no initial payment was selected
GET  /receipts/{receipt_id}/reconciliation
POST /receipts/{receipt_id}/approve
GET  /receipts/{receipt_id}/audit-events
```

Approval requires at least one item and payment and:

```text
stated total = item total = payment total
```

## OCR receipt workflow

Use the UI **Scan receipt** flow or:

```text
POST /receipt-captures
POST /receipt-captures/{capture_id}/ocr
GET  /receipt-captures/{capture_id}
POST /receipts
```

Review all suggestions before creating the draft. OCR can suggest merchant
branch, address, date/time, total, items, category, payment method and receipt
number. Azure structured fields are preferred; conservative raw-text fallbacks
support German addresses and labelled receipt numbers.

Payment suggestions use unique last-four matching first, followed by unique
provider/type matching. Ambiguous matches remain unselected.

## Duplicate detection

- Exact same image: `409 Conflict` at upload.
- Strong business match: receipt creation is blocked and the UI links to the
  existing receipt.
- Same merchant/date/total without stronger evidence: warning only.
- Voided receipts do not block a new active receipt-number identity.

## Categories

Expense:

```text
groceries, rent, health_insurance, transport, university_fees, utilities,
subscriptions, dining, shopping, travel, other
```

Income:

```text
salary_payslip, freelance, interest, gift, refund, benefits, other
```

## Dashboard and exports

```text
GET /dashboard?year=YYYY&month=MM
GET /dashboard/export.csv?year=YYYY&month=MM
```

The dashboard uses approved receipts in the household default currency. It
shows KPI cards, category donut chart, 12-month income/expense bars, top monthly
and yearly merchants, frequent products and data-quality warnings.

Use **Print / PDF** in the UI for a print-formatted report.

## Income

```json
POST /income
{
  "source": "Employer",
  "income_type": "salary",
  "category": "salary_payslip",
  "received_date": "2026-07-23",
  "amount": "2500.00",
  "currency": "EUR",
  "destination_payment_method_id": "PAYMENT_METHOD_ID",
  "notes": null
}
```

## Multi-household behavior

One user may have active memberships in multiple households. The user switches
the active household in the UI. Role and access are evaluated separately per
membership, and all financial queries are scoped using the authenticated
`household_id`.

## Corrections and safety

Draft receipt headers, items and payments can be corrected through `PATCH`.
Approved receipts are immutable but can be voided. Database constraints enforce
household scope, payment ownership, valid states and duplicate receipt numbers.

Do not update financial rows directly in PostgreSQL because direct changes
bypass API validation and audit-event creation.
