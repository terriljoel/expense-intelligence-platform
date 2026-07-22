# Expense Intelligence Platform

A local-first income and expense tracker built with FastAPI and PostgreSQL.
FastAPI serves both the JSON API and a small phone-friendly web interface, so
there is no separate Node.js frontend to install or run.

The web interface supports receipts, receipt items, payments, reconciliation,
approval, income entries, merchants, payment methods, and a simple household
balance. Dashboard totals currently summarize the default EUR currency.

## Start the application

Run these commands from the project root.

### 1. Start PostgreSQL

```powershell
docker compose up -d db
```

- `docker compose` reads `docker-compose.yml`.
- `up` creates and starts the configured services.
- `-d` runs the database in the background.
- `db` starts only the PostgreSQL service.

### 2. Create and activate the Python environment

Create the project-local environment once and install the dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r apps\api\requirements.txt
```

On later PowerShell sessions, only activation is needed:

```powershell
.\.venv\Scripts\Activate.ps1
```

For Command Prompt (`cmd`), use the portable helper:

```bat
activate_venv.bat
```

### 3. Prepare the database

```powershell
cd apps\api
python -m alembic upgrade head
python -m app.db.seed
```

- `python -m` runs an installed Python module.
- `alembic upgrade head` applies every pending database migration.
- `app.db.seed` creates the local owner, household, and membership when needed.

### 4. Start FastAPI

```powershell
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- `app.main:app` means the `app` FastAPI object inside `app/main.py`.
- `--reload` restarts the server when Python or frontend files change.
- `--host 0.0.0.0` permits access from another device on the same network.
- `--port 8000` makes the application listen on port 8000.

Open these addresses on the computer:

- Web interface: <http://127.0.0.1:8000/>
- Swagger API: <http://127.0.0.1:8000/docs>
- Database readiness: <http://127.0.0.1:8000/health/ready>

## Open it on a phone

The phone does not need Python or Node.js. It only needs a browser and must be
connected to the same Wi-Fi network as the computer.

1. Keep FastAPI running with `--host 0.0.0.0` as shown above.
2. Run `ipconfig` and find the computer's **IPv4 Address**, for example
   `192.168.1.25`.
3. On the phone, open `http://192.168.1.25:8000/`, replacing the example with
   the computer's real IPv4 address.
4. If Windows asks about firewall access, allow Python on **Private networks**.

This local version uses the seeded single owner/admin automatically. Real login
and additional household users can be added later without changing the receipt
domain model.

## Run checks

From `apps\api` with the Python environment active:

```powershell
python -m pytest
python -m ruff check .
```

- `pytest` runs the automated API and UI-serving tests.
- `ruff check .` checks Python formatting and common code problems.
