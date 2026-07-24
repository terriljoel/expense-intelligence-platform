# Current local operations guide

This guide applies through migration `016_receipt_duplicates`. See
[`CURRENT_IMPLEMENTATION.md`](./CURRENT_IMPLEMENTATION.md) for the feature and
schema inventory.

## Start PostgreSQL

From the repository root:

```bat
docker compose up -d db
docker compose ps
```

- `up` creates or starts the configured service.
- `-d` runs it in the background.
- `db` selects only PostgreSQL.
- `ps` displays service status and port mappings.

## Apply schema migrations

```bat
cd apps\api
python -m alembic upgrade head
python -m alembic current
```

Expected current revision:

```text
016_receipt_duplicates
```

Do not run `stamp` on an existing database unless the schema was created
manually and you intentionally need to register an already-applied revision.

## Start FastAPI for computer and phone

```bat
cd apps\api
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- `--reload` restarts the development server after source changes.
- `--host 0.0.0.0` listens on the computer's network interfaces.
- `--port 8000` uses TCP port 8000.

Computer:

```text
http://127.0.0.1:8000
```

Phone example:

```text
http://192.168.0.102:8000
```

Both devices must be on the same network. Allow Python/Uvicorn through Windows
Firewall on the private network. Close and reopen the phone tab after UI
updates; application assets use versioned URLs to avoid stale mobile charts.

## Important `.env` configuration

```dotenv
DATABASE_URL=postgresql+psycopg://expense_app:LOCAL_PASSWORD@localhost:5432/expense_intelligence

RECEIPT_STORAGE_PROVIDER=local
RECEIPT_IMAGE_DIR=data/receipt-images

OCR_PROVIDER=tesseract
TESSERACT_COMMAND=tesseract
TESSERACT_LANGUAGE=deu+eng
```

Azure alternatives:

```dotenv
RECEIPT_STORAGE_PROVIDER=azure_blob
AZURE_STORAGE_CONNECTION_STRING=
AZURE_STORAGE_ACCOUNT_URL=
AZURE_STORAGE_CONTAINER=receipt-images

OCR_PROVIDER=azure
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=
AZURE_DOCUMENT_INTELLIGENCE_KEY=
AZURE_DOCUMENT_INTELLIGENCE_LOCALE=de-DE
```

Never commit `.env`. YAML also stores secrets as plaintext and is not safer.

## PostgreSQL shell

```bat
docker compose exec db psql -U expense_app -d expense_intelligence
```

Useful commands:

```text
\dt
\dv
\d receipts
\d receipt_captures
\q
```

## Run checks

```bat
cd apps\api
python -m pytest -q -p no:cacheprovider
python -m ruff check --no-cache app tests
python -m alembic current
```

The exact number of tests changes as features are added; all selected tests and
lint checks should pass.

## Backup, archive and reset

In the UI, open **Setup -> Data maintenance** as an owner or admin.

1. Download the household ZIP archive.
2. Review record counts.
3. Enter `RESET <household name>` exactly.
4. Confirm the permanent transactional-data reset.

Reset preserves users, memberships, household settings, merchants and payment
methods. It removes receipts, OCR captures/images, income and receipt audit
history for the active household only.

