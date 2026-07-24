# Expense Intelligence Platform

A local-first income and expense tracker built with FastAPI and PostgreSQL.
FastAPI serves both the JSON API and a small phone-friendly web interface, so
there is no separate Node.js frontend to install or run.

The web interface supports receipts, receipt items, payments, reconciliation,
approval, income entries, merchants, payment methods, household invitations,
and a simple household balance. Dashboard totals currently summarize the
default EUR currency.

Receipt images can be captured directly from a phone camera or selected from a
computer. Images stay in private local storage, OCR runs through local
Tesseract, and detected values are always shown for review before a draft is
created.

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

### Install local OCR

Install Tesseract 5 for Windows using the installer linked by the
[official Tesseract installation guide](https://tesseract-ocr.github.io/tessdoc/Installation.html#windows).
Include both German (`deu`) and English (`eng`) language data. Confirm the
installation in a new terminal:

```powershell
tesseract --version
tesseract --list-langs
```

If `tesseract` is not on `PATH`, set its full executable path in `.env`:

```dotenv
TESSERACT_COMMAND=C:\Program Files\Tesseract-OCR\tesseract.exe
TESSERACT_LANGUAGE=deu+eng
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
python -m app.db.set_owner_password --email your-email@example.com
```

- `python -m` runs an installed Python module.
- `alembic upgrade head` applies every pending database migration.
- `app.db.seed` creates the local owner, household, and membership when needed.
- `app.db.set_owner_password` securely prompts for the owner's password, stores
  only its Argon2 hash, and revokes older login sessions. Run it once initially
  and again whenever the password must be changed.

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

### Capture and read a receipt

1. Open **Receipts** and select **Scan receipt**.
2. Take a photo or select a JPEG, PNG, or WebP image up to 10 MB.
3. Wait for local OCR, then compare the suggested merchant, date, and total
   with the image and recognized text.
4. Select **Review and create draft**, correct any value, and create the draft.
5. Add or correct line items and payment details before approval.

The image and OCR text are household-scoped and are never exposed as public
static files. A SHA-256 check rejects duplicate image captures. OCR failure does
not block manual entry, and OCR output never approves a receipt automatically.

## Open it on a phone

The phone does not need Python or Node.js. It only needs a browser and must be
connected to the same Wi-Fi network as the computer.

1. Keep FastAPI running with `--host 0.0.0.0` as shown above.
2. Run `ipconfig` and find the computer's **IPv4 Address**, for example
   `192.168.1.25`.
3. On the phone, open `http://192.168.1.25:8000/`, replacing the example with
   the computer's real IPv4 address.
4. If Windows asks about firewall access, allow Python on **Private networks**.

This version uses local email/password authentication. The session is stored
server-side and the browser receives only an HTTP-only random session token.

## Add another household user

1. Sign in as the household owner or an admin.
2. Open **Members**.
3. Enter the new user's email, choose `member` or `admin`, and select
   **Create invitation**.
4. Copy the displayed link and send it privately to that person.
5. They open the link, enter their name and a password of at least 12
   characters, then sign in.

The raw invitation token appears only in the newly generated link; PostgreSQL
stores its SHA-256 hash. Invitations expire after seven days by default. Change
`INVITATION_HOURS` in `.env` if a different local expiry is needed. All
household members see shared receipts and income, while payment methods remain
owned by individual users. Only owners and admins can manage invitations.

### Work with multiple households

The household selector in the header controls the active household. Every
receipt, income entry, merchant, payment method, member list, and invitation is
loaded using that active household's ID.

- Select another household to switch without signing out.
- Select **+ New** to create another household; the creator becomes its owner.
- An existing user can open an invitation link, sign in, and join an additional
  household without creating another account.

Switching updates the server-side session only after PostgreSQL confirms that
the signed-in user is a member of the requested household. Data is reloaded
after the switch, preventing records from the previous household from remaining
on screen.

### Manage a household

Open **Members** to rename the active household, change its default currency,
change roles, remove another member, or leave. Owners and admins can manage
settings and members; only an owner can grant owner access or change an owner's
role. The final owner cannot be demoted, removed, or leave until another owner
has been promoted.

Member removal deactivates access and revokes that household's sessions.
Historical receipts, income, payments, and audit records remain visible with
the original person's display name.

Phone access currently uses plain HTTP on the private Wi-Fi network. Do not
expose port 8000 to the public internet. Before internet deployment, add HTTPS,
set `SESSION_COOKIE_SECURE=true`, and add login rate limiting.

## Run checks

From `apps\api` with the Python environment active:

```powershell
python -m pytest
python -m ruff check .
```

- `pytest` runs the automated API and UI-serving tests.
- `ruff check .` checks Python formatting and common code problems.
