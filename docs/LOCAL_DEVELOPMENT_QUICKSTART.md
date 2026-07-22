# Local development quick-start

This guide starts the Expense Intelligence PostgreSQL database with Docker and
runs the FastAPI application locally on Windows.

## 1. Prerequisites

Install and start:

- Docker Desktop (Linux containers)
- Python 3.11+
- Git

Open **Command Prompt** and move to the repository root:

```bat
cd /d "C:\Users\HiWi\Desktop\Terril\01_nextcloud\Germany\DATA SCIENCE\03 PROJECT\02 Expense Tracker\expense-intelligence-platform"
```

## 2. Environment variables

The root `.env` file must define:

```dotenv
POSTGRES_DB=expense_intelligence
POSTGRES_USER=expense_app
POSTGRES_PASSWORD=choose-a-local-password
DATABASE_URL=postgresql+psycopg://expense_app:choose-a-local-password@localhost:5432/expense_intelligence
```

Use the same password in `POSTGRES_PASSWORD` and `DATABASE_URL`. Never commit
`.env` to Git.

## 3. Start PostgreSQL

From the repository root:

```bat
docker compose up -d db
docker compose ps
```

The database should show `running` or `healthy`, with port `5432` exposed.

View database logs:

```bat
docker compose logs db
```

Stop the containers without deleting data:

```bat
docker compose stop
```

Start them again:

```bat
docker compose start
```

## 4. Initialize a brand-new database

Run the baseline schema once in **Command Prompt**:

```bat
type database\migrations\001_initial_schema.sql | docker compose exec -T db psql -v ON_ERROR_STOP=1 -U expense_app -d expense_intelligence
```

Register the baseline and apply all newer Alembic migrations:

```bat
cd apps\api
python -m alembic stamp 001_initial_schema
python -m alembic upgrade head
python -m alembic current
cd ..\..
```

For the existing local database, normally run only:

```bat
cd apps\api
python -m alembic upgrade head
cd ..\..
```

## 5. Install the Python dependencies

Create and activate a virtual environment if one is not already active:

```bat
python -m venv .venv
.venv\Scripts\activate
```

Install the API dependencies:

```bat
python -m pip install --upgrade pip
python -m pip install -r apps\api\requirements.txt
```

## 6. Seed the local owner

The development seed creates the local user, household, owner membership and
Cash payment method. It is safe to run more than once.

```bat
cd apps\api
python -m app.db.seed
cd ..\..
```

## 7. Query PostgreSQL

Start the PostgreSQL client:

```bat
docker compose exec db psql -U expense_app -d expense_intelligence
```

The prompt changes to something similar to:

```text
expense_intelligence=#
```

Now SQL commands will work:

```sql
SELECT current_database(), current_user;
SELECT * FROM users;
SELECT * FROM payment_methods;
SELECT * FROM receipts ORDER BY purchase_date DESC;
SELECT * FROM receipt_reconciliation;
SELECT sequence_number, event_type, event_data
FROM audit_events
ORDER BY sequence_number;
```

Useful `psql` commands:

```text
\dt                 list tables
\dv                 list views
\d receipts         describe the receipts table
\q                  exit psql
```

If the prompt is `/ #`, you are in the Linux shell, not `psql`. Run the `psql`
command first.

## 8. Start FastAPI

Keep PostgreSQL running. Open a second terminal from the repository root:

```bat
cd apps\api
python -m uvicorn app.main:app --reload
```

Open these addresses:

- API health: <http://127.0.0.1:8000/health/ready>
- Swagger API documentation: <http://127.0.0.1:8000/docs>
- OpenAPI JSON: <http://127.0.0.1:8000/openapi.json>

A request for `/favicon.ico` may return `404`. That is harmless because the API
does not provide a browser icon.

Stop FastAPI with `Ctrl+C`.

## 9. Test the manual receipt workflow

Use Swagger in this order:

1. `POST /merchants`
2. `GET /payment-methods`
3. `POST /receipts`
4. `POST /receipts/{receipt_id}/items`
5. `POST /receipts/{receipt_id}/payments`
6. `GET /receipts/{receipt_id}/reconciliation`
7. `POST /receipts/{receipt_id}/approve`
8. `GET /receipts/{receipt_id}/audit-events`

The receipt can be approved only when its stated total, item total and payment
total are equal.

## 10. Run verification

From `apps\api` with PostgreSQL running:

```bat
python -m pytest -q
python -m alembic check
python -m ruff check app tests
```

Expected results:

```text
24 passed
No new upgrade operations detected.
All checks passed!
```

## Command Prompt versus PowerShell

`type` is the Command Prompt command for reading a file. `Get-Content` is a
PowerShell command.

PowerShell equivalent of the baseline migration command:

```powershell
Get-Content -Raw database/migrations/001_initial_schema.sql |
    docker compose exec -T db psql -v ON_ERROR_STOP=1 -U expense_app -d expense_intelligence
```

Do not enter `Get-Content` in Command Prompt and do not enter SQL directly at
the Docker `/ #` shell prompt.

## Common problems

### Docker pipe cannot be found

```text
open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified
```

Start Docker Desktop and wait until the engine reports that it is running.

### PostgreSQL variables are blank

```text
The "POSTGRES_DB" variable is not set
```

Confirm that `.env` exists in the same directory as `docker-compose.yml`, then
run Docker Compose from the repository root.

### Python cannot import `app`

```text
ModuleNotFoundError: No module named 'app'
```

Run FastAPI, Alembic and pytest from `apps\api`:

```bat
cd apps\api
python -m pytest -q
```

### Database readiness fails

Check the container and logs:

```bat
docker compose ps
docker compose logs db
```

Then confirm that `DATABASE_URL` uses `localhost:5432` when FastAPI runs on the
Windows host.
