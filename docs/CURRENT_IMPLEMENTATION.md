# Expense Intelligence Platform - current implementation

This document describes the application at PostgreSQL migration
`016_receipt_duplicates`.

## Implemented capabilities

- FastAPI API, Swagger UI and responsive browser/phone interface.
- PostgreSQL running locally through Docker Compose.
- Local authentication with server-side sessions.
- Multiple households per user with owner, admin and member roles.
- Strict `household_id` scoping for financial and configuration data.
- Household switching, invitations and member administration.
- Merchants identified per household and branch using normalized name and address.
- User-owned payment methods and split receipt payments.
- Expense receipts, line items, income, reconciliation, approval and voiding.
- Expense and income categories.
- Append-only receipt audit events.
- Receipt image storage using local files or private Azure Blob Storage.
- OCR using local Tesseract or Azure Document Intelligence.
- OCR suggestions for merchant, branch address, date, time, totals, items,
  payment method and receipt number.
- Automatic merchant-branch creation when a matching branch does not exist.
- Exact-image and OCR business-field duplicate detection.
- Dashboard charts, household analytics, CSV export and print/PDF reporting.
- ZIP household archive and admin-only transactional-data reset.

## Current ER diagram

Open [`../diagrams/expense-intelligence-multi-user.drawio`](../diagrams/expense-intelligence-multi-user.drawio)
in Draw.io. It represents the schema through migration 016.

Dashboard metrics, exports and archives are derived/application behavior and do
not introduce dashboard or export tables.

## Receipt capture flow

```text
Upload image
  -> SHA-256 exact-image duplicate check
  -> private local/Azure Blob storage
  -> OCR
  -> structured fields plus conservative raw-text fallbacks
  -> merchant branch match/create
  -> payment-method suggestion
  -> receipt-number and business-field duplicate check
  -> user review
  -> draft receipt, OCR items and optional payment
  -> reconciliation
  -> approval
```

Azure commonly returns `MerchantAddress` as a structured `valueAddress` object.
The adapter supports that structure and falls back to a German street plus
postal-code/city parser when the address exists only in raw OCR text.

## Duplicate receipt rules

1. The exact same image is rejected using
   `household_id + image_sha256`.
2. A different photo is a strong duplicate when it matches either:
   - merchant branch + date + normalized receipt number; or
   - merchant branch + date + time + total + currency.
3. Merchant branch + date + total is a possible duplicate warning because two
   legitimate purchases can share those values.
4. PostgreSQL also has a partial unique index for active receipts using
   household, merchant, date and normalized receipt number.

## Categories

Expense categories:

```text
groceries, rent, health_insurance, transport, university_fees, utilities,
subscriptions, dining, shopping, travel, other
```

Income categories:

```text
salary_payslip, freelance, interest, gift, refund, benefits, other
```

## Dashboard and exports

The dashboard uses approved receipts only and calculates in the household's
default currency. Other currencies are counted but not incorrectly added to the
default-currency total.

It provides monthly expenditure, income and balance, year-to-date spending,
category breakdown, monthly trend, top merchants, top products, average and
largest receipt, draft warnings and explanatory insights.

Exports:

- `GET /dashboard/export.csv?year=YYYY&month=MM`
- **Print / PDF** in the dashboard UI
- `GET /maintenance/archive` for the complete household ZIP archive

## Storage and OCR configuration

```dotenv
RECEIPT_STORAGE_PROVIDER=local
RECEIPT_IMAGE_DIR=data/receipt-images

# Alternative private Blob storage
AZURE_STORAGE_CONNECTION_STRING=
AZURE_STORAGE_ACCOUNT_URL=
AZURE_STORAGE_CONTAINER=receipt-images

OCR_PROVIDER=tesseract
TESSERACT_COMMAND=tesseract
TESSERACT_LANGUAGE=deu+eng

# Alternative Azure OCR
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=
AZURE_DOCUMENT_INTELLIGENCE_KEY=
AZURE_DOCUMENT_INTELLIGENCE_LOCALE=de-DE
```

Do not commit `.env`. YAML is not safer for secrets. For Azure deployment use
App Service environment variables, Managed Identity and Key Vault references.

## Database migrations

From `apps/api`:

```bat
python -m alembic upgrade head
python -m alembic current
```

The expected current revision is:

```text
016_receipt_duplicates
```

## Main endpoints

```text
/auth                 authentication and household switching
/household            settings and membership administration
/invitations          household invitation acceptance
/merchants            household merchant branches
/payment-methods      current user's methods in the active household
/receipt-captures     upload, image access and OCR
/receipts             receipt workflow, items, payments and audit events
/income               household income
/dashboard            analytics
/dashboard/export.csv analytics CSV export
/maintenance          preview, archive and reset
```

## Maintenance safety

Only an owner or admin can access maintenance operations. Reset requires the
exact phrase `RESET <household name>` and preserves users, memberships,
household settings, merchants and payment methods while removing transactional
receipts, OCR captures/images, income and receipt audit history.

Always download an archive before resetting data.
