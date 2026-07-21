# Expense Intelligence database

PostgreSQL 16 is the source of truth. SQLAlchemy maps the tables, Alembic tracks
schema versions, and FastAPI opens one transaction per request.

## Current Milestone 1 schema

| Object | Purpose |
|---|---|
| `users` | Application identity; the local owner is currently seeded |
| `households` | Tenant and currency boundary |
| `household_members` | User-to-household membership and role |
| `merchants` | Household-scoped merchant names |
| `payment_methods` | User-owned cash, card, transfer, or wallet method |
| `receipts` | Receipt header, lifecycle, total, source, and image metadata |
| `receipt_items` | Ordered product, discount, fee, tax, or adjustment lines |
| `receipt_payments` | One or more payment allocations for a receipt |
| `audit_events` | Immutable, deterministically ordered receipt history |
| `receipt_reconciliation` | View comparing stated, item, and payment totals |

Important rules are enforced twice where useful: once by request validation and
again by PostgreSQL constraints. Household-scoped composite foreign keys prevent
cross-household references. Receipt approval also locks the receipt row and is
allowed only when it has items, payments, and both totals equal `stated_total`.
Audit events cannot be updated or deleted.

Expense allocation between household members is intentionally deferred. The
current owner pays the recorded receipt. The existing membership and
user-scoped payment design supports adding the second user later without
redesigning receipt ownership.

## Start and initialize a new local database

From the repository root:

```text
docker compose up -d db
```

Apply the baseline SQL. In **Command Prompt**:

```bat
type database\migrations\001_initial_schema.sql | docker compose exec -T db psql -v ON_ERROR_STOP=1 -U expense_app -d expense_intelligence
```

Then register the baseline and apply later migrations:

```bat
cd apps\api
python -m alembic stamp 001_initial_schema
python -m alembic upgrade head
cd ..\..
```

In **PowerShell**, replace the first pipeline with:

```powershell
Get-Content -Raw database/migrations/001_initial_schema.sql |
    docker compose exec -T db psql -v ON_ERROR_STOP=1 -U expense_app -d expense_intelligence
```

Do not apply `002` or `003` manually when Alembic is used; `alembic upgrade
head` applies them. The numbered SQL copies are retained as readable PostgreSQL
artifacts.

Seed the local owner, household, and cash payment method:

```bat
cd apps\api
python -m app.db.seed
```

The seed is idempotent, so running it again does not duplicate data.

## Normal migration workflow

After changing a SQLAlchemy model:

```bat
cd apps\api
python -m alembic revision --autogenerate -m "short description"
python -m alembic upgrade head
python -m alembic check
```

Review every generated migration before applying it. Never edit a migration
that has already been used by a shared database; add a new revision instead.

Useful status commands:

```bat
python -m alembic current
python -m alembic history
python -m alembic heads
```

## Query the database

Open PostgreSQL's interactive client from Docker Desktop Exec or a terminal:

```text
psql -U expense_app -d expense_intelligence
```

From the host terminal, use:

```text
docker compose exec db psql -U expense_app -d expense_intelligence
```

Useful `psql` commands and SQL:

```sql
\dt
\dv
\d receipts
SELECT current_database(), current_user;
SELECT * FROM receipts ORDER BY purchase_date DESC;
SELECT * FROM receipt_reconciliation;
SELECT sequence_number, event_type, event_data, created_at
FROM audit_events
ORDER BY sequence_number;
\q
```

`SELECT` is SQL and only works after starting `psql`. A `/ #` prompt in Docker
Desktop is the Linux shell, not PostgreSQL.

## Verification

Run the rollback-only SQL verification from the repository root:

```bat
type database\verify_schema.sql | docker compose exec -T db psql -v ON_ERROR_STOP=1 -U expense_app -d expense_intelligence
```

Run the application integration suite and migration comparison:

```bat
cd apps\api
python -m pytest -q
python -m alembic check
```

The SQL verification creates a temporary receipt workflow and rolls it back.
The Python tests also run inside rollback transactions, so they do not leave
test receipts in the local database.

## Backup and restore

Use **Command Prompt** for these binary redirection commands. Create a backup:

```bat
if not exist backups mkdir backups
docker compose exec -T db pg_dump -U expense_app -d expense_intelligence -Fc > backups\expense_intelligence.dump
```

Inspect the backup without restoring it:

```bat
docker compose exec -T db pg_restore --list < backups\expense_intelligence.dump
```

Restore into an empty database:

```bat
docker compose exec -T db createdb -U expense_app expense_restore
docker compose exec -T db pg_restore -v -U expense_app -d expense_restore < backups\expense_intelligence.dump
```

Restoring into `expense_restore` protects the working database. Verify the copy
before replacing anything. A command using `--clean` can remove existing schema
objects and should only be used when that destructive behavior is intended.

## Data ownership and secrets

- Keep `.env` out of Git; commit only an `.env.example` without passwords.
- Store money as `NUMERIC`, never floating point.
- Store timestamps as `TIMESTAMPTZ` and display them in the user's timezone.
- Keep receipt images in object storage later; PostgreSQL stores only their key
  and SHA-256 hash.
- Back up before destructive migrations and test restore regularly.
