# Docker, PostgreSQL and FastAPI — explained commands

This guide runs the local database and API on Windows. Every command is
followed by an explanation of its parts and options.

## 1. Open the project

Run in **Command Prompt**:

```bat
cd /d "C:\Users\HiWi\Desktop\Terril\01_nextcloud\Germany\DATA SCIENCE\03 PROJECT\02 Expense Tracker\expense-intelligence-platform"
```

| Part | Meaning |
|---|---|
| `cd` | Change the current directory. |
| `/d` | Also change the drive, for example from `D:` to `C:`. |
| Quoted path | Project location. Quotes are necessary because it contains spaces. |

## 2. Understand `.env`

The `.env` file beside `docker-compose.yml` contains:

```dotenv
POSTGRES_DB=expense_intelligence
POSTGRES_USER=expense_app
POSTGRES_PASSWORD=choose-a-local-password
DATABASE_URL=postgresql+psycopg://expense_app:choose-a-local-password@localhost:5432/expense_intelligence
```

| Name | Meaning |
|---|---|
| `POSTGRES_DB` | Database created by the PostgreSQL image. |
| `POSTGRES_USER` | PostgreSQL login used by the application. |
| `POSTGRES_PASSWORD` | Password for that login. |
| `DATABASE_URL` | Address SQLAlchemy uses to connect. |

The URL pattern is:

```text
postgresql+psycopg://USER:PASSWORD@HOST:PORT/DATABASE
```

| URL part | Meaning |
|---|---|
| `postgresql` | Database system. |
| `+psycopg` | Python driver used by SQLAlchemy. |
| `USER:PASSWORD` | PostgreSQL credentials. |
| `localhost` | Database is reachable on this computer. |
| `5432` | Default PostgreSQL port. |
| `/expense_intelligence` | Database to open. |

Do not commit `.env` because it contains a password.

## 3. Start PostgreSQL with Docker

```bat
docker compose up -d db
```

| Part | Meaning |
|---|---|
| `docker` | Docker command-line program. |
| `compose` | Read and use `docker-compose.yml`. |
| `up` | Create the service container if needed and start it. |
| `-d` | Detached mode: keep it running in the background. |
| `db` | Start only the service named `db`. |

Check its status:

```bat
docker compose ps
```

`ps` means process status. It displays the container state, health and ports.

Read its logs:

```bat
docker compose logs db
```

`logs` prints container output; `db` selects the PostgreSQL service.

Follow new messages continuously:

```bat
docker compose logs -f db
```

`-f` means **follow**. Press `Ctrl+C` to stop following; this does not stop the
database.

Stop without deleting data:

```bat
docker compose stop
```

`stop` stops the containers but preserves the container and database volume.

Start existing stopped containers:

```bat
docker compose start
```

`start` starts an existing container. Unlike `up`, it does not create one.

## 4. Initialize a brand-new database

Run the baseline once in **Command Prompt**:

```bat
type database\migrations\001_initial_schema.sql | docker compose exec -T db psql -v ON_ERROR_STOP=1 -U expense_app -d expense_intelligence
```

| Part | Meaning |
|---|---|
| `type FILE` | Read the SQL file and send its text to standard output. |
| `|` | Pipe the output on the left into the command on the right. |
| `docker compose exec` | Execute a program in an already-running Compose container. |
| `-T` | Disable the interactive terminal so piped input works correctly. |
| `db` | Use the PostgreSQL service container. |
| `psql` | PostgreSQL command-line client. |
| `-v ON_ERROR_STOP=1` | Stop immediately if a SQL statement fails. |
| `-U expense_app` | Connect as user `expense_app`; `-U` means user. |
| `-d expense_intelligence` | Open that database; `-d` means database. |

Now record the baseline and apply later migrations:

```bat
cd apps\api
python -m alembic stamp 001_initial_schema
python -m alembic upgrade head
python -m alembic current
cd ..\..
```

| Command or part | Meaning |
|---|---|
| `cd apps\api` | Enter the folder containing `alembic.ini`. |
| `python -m MODULE` | Run a module with the currently selected Python. |
| `alembic` | Database migration tool. |
| `stamp 001_initial_schema` | Record that the manually executed baseline exists without executing it again. |
| `upgrade head` | Apply every missing migration through the newest revision. |
| `current` | Display the revision stored in the database. |
| `cd ..\..` | Go up two folders to the project root. |

Only use `stamp` after manually applying the baseline to a new database. For an
existing database, normally run only:

```bat
cd apps\api
python -m alembic upgrade head
cd ..\..
```

## 5. Create the Python environment

```bat
python -m venv .venv
```

| Part | Meaning |
|---|---|
| `python` | Start the installed Python interpreter. |
| `-m venv` | Run Python's built-in virtual-environment module. |
| `.venv` | Folder where the isolated environment is created. |

Activate it in Command Prompt:

```bat
.venv\Scripts\activate
```

This changes the current terminal so `python` and `pip` use `.venv`. You must
activate it again in each new terminal.

Install dependencies:

```bat
python -m pip install --upgrade pip
python -m pip install -r apps\api\requirements.txt
```

| Part | Meaning |
|---|---|
| `python -m pip` | Run the `pip` belonging to the active Python. |
| `install` | Install packages. |
| `--upgrade pip` | Update `pip` itself if a newer version is available. |
| `-r FILE` | Read packages and versions from a requirements file. |
| `apps\api\requirements.txt` | Dependency list for this API. |

## 6. Seed development data

```bat
cd apps\api
python -m app.db.seed
cd ..\..
```

`app.db.seed` means the module `app/db/seed.py`. It inserts the local owner,
household, owner membership and Cash payment method when they do not already
exist. The seed is idempotent: repeated runs do not duplicate these rows.

## 7. Query PostgreSQL

```bat
docker compose exec db psql -U expense_app -d expense_intelligence
```

| Part | Meaning |
|---|---|
| `docker compose exec db` | Run the following program inside the `db` container. |
| `psql` | Start the interactive PostgreSQL client. |
| `-U expense_app` | Log in as `expense_app`. |
| `-d expense_intelligence` | Open the application database. |

There is no `-T` here because this time an interactive terminal is required.
The prompt should become similar to:

```text
expense_intelligence=#
```

Run queries:

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

| SQL part | Meaning |
|---|---|
| `SELECT` | Read data without changing it. |
| `current_database()` | Return the open database name. |
| `current_user` | Return the logged-in PostgreSQL user. |
| `*` | Return every column. |
| `FROM name` | Select the table or view to read. |
| `ORDER BY column` | Sort using that column. |
| `DESC` | Descending order, newest or largest first. |
| `;` | End and execute a SQL statement in `psql`. |

Useful `psql` commands:

```text
\dt
\dv
\d receipts
\q
```

| Command | Meaning |
|---|---|
| `\dt` | List tables. |
| `\dv` | List views. |
| `\d receipts` | Describe columns and constraints of `receipts`. |
| `\q` | Quit `psql`. |

Backslash commands belong to `psql`; they are not SQL. A `/ #` prompt is the
container's Linux shell, so start `psql` before entering SQL.

## 8. Start FastAPI

Keep PostgreSQL running. Open a second Command Prompt:

```bat
cd /d "C:\Users\HiWi\Desktop\Terril\01_nextcloud\Germany\DATA SCIENCE\03 PROJECT\02 Expense Tracker\expense-intelligence-platform"
.venv\Scripts\activate
cd apps\api
python -m uvicorn app.main:app --reload
```

| Part | Meaning |
|---|---|
| `python -m uvicorn` | Run the Uvicorn ASGI web server with the active Python. |
| `app.main` | Import `app/main.py` as a Python module. |
| `:app` | Use the FastAPI object named `app` from that module. |
| `--reload` | Watch source files and restart after changes. Use only in development. |

By default Uvicorn listens at `127.0.0.1:8000`. `127.0.0.1` means this
computer, and `8000` is the network port.

Open:

- Health check: <http://127.0.0.1:8000/health/ready>
- Swagger: <http://127.0.0.1:8000/docs>
- OpenAPI definition: <http://127.0.0.1:8000/openapi.json>

Stop FastAPI with `Ctrl+C`. A `404` for `/favicon.ico` is harmless; the API does
not provide a browser icon.

## 9. Test through Swagger

Use endpoints in this order:

1. `POST /merchants`
2. `GET /payment-methods`
3. `POST /receipts`
4. `POST /receipts/{receipt_id}/items`
5. `POST /receipts/{receipt_id}/payments`
6. `GET /receipts/{receipt_id}/reconciliation`
7. `POST /receipts/{receipt_id}/approve`
8. `GET /receipts/{receipt_id}/audit-events`

`POST` creates or changes data. `GET` reads data. `{receipt_id}` is a
placeholder that must be replaced with the UUID returned when the receipt was
created.

## 10. Run automated checks

From `apps\api`, with PostgreSQL running:

```bat
python -m pytest -q
python -m alembic check
python -m ruff check app tests
```

| Command or option | Meaning |
|---|---|
| `python -m pytest` | Discover and run the automated tests. |
| `-q` | Quiet mode: show compact results. |
| `python -m alembic check` | Compare SQLAlchemy models with PostgreSQL and report schema drift. |
| `python -m ruff` | Run the Ruff code-quality tool. |
| `check` | Find import and code-quality violations. |
| `app tests` | Check both directories. |

## 11. PowerShell baseline command

Command Prompt uses `type`; PowerShell uses `Get-Content`:

```powershell
Get-Content -Raw database/migrations/001_initial_schema.sql |
    docker compose exec -T db psql -v ON_ERROR_STOP=1 -U expense_app -d expense_intelligence
```

| Part | Meaning |
|---|---|
| `Get-Content` | PowerShell command for reading a file. |
| `-Raw` | Return the entire file as one string rather than separate lines. |
| `|` | Pipe that SQL into `psql`. |

The Docker and `psql` options mean the same as in section 4.

## 12. Common errors

### Docker Desktop engine is unavailable

```text
open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified
```

Start Docker Desktop and wait for its Linux engine to report that it is
running. Then retry `docker compose up -d db`.

### Compose variables are blank

```text
The "POSTGRES_DB" variable is not set
```

Confirm `.env` is beside `docker-compose.yml` and run Compose from the project
root. Compose automatically reads that `.env` from its working directory.

### Python cannot import `app`

```text
ModuleNotFoundError: No module named 'app'
```

Run Uvicorn, Alembic and pytest from `apps\api`, because that directory contains
the `app` package:

```bat
cd apps\api
python -m pytest -q
```

### Check database readiness

```bat
docker compose ps
docker compose logs db
```

The first command checks container state; the second reads PostgreSQL startup
messages. When FastAPI runs directly on Windows, `DATABASE_URL` should use
`localhost:5432`.
