# GitHub CI/CD setup

The workflow `.github/workflows/pipeline.yml` tests every pull request and push.
After a successful test run on `main`, it migrates Neon, publishes a versioned
container image to Azure Container Registry (ACR), and deploys that exact image
to Azure Web App.

## GitHub environment

In the repository, open **Settings → Environments → New environment** and create
an environment named `production`. Add an approval rule if you want each
production deployment to wait for manual approval.

## Repository variables

Open **Settings → Secrets and variables → Actions → Variables** and add:

| Variable | Example | Meaning |
|---|---|---|
| `ACR_LOGIN_SERVER` | `azdockerregistry.azurecr.io` | ACR login server, without `https://` |
| `ACR_REPOSITORY` | `expense-intelligence-api` | Container repository name |
| `AZURE_WEBAPP_NAME` | `expense-intelligence-app` | Azure resource name, not its URL |

## Repository secrets

On the **Secrets** tab add:

| Secret | Where to obtain it |
|---|---|
| `NEON_DATABASE_URL` | Neon connection string using `postgresql+psycopg://` and `sslmode=require` |
| `ACR_USERNAME` | ACR → Access keys → Username |
| `ACR_PASSWORD` | ACR → Access keys → Password 1 or Password 2 |
| `AZURE_WEBAPP_PUBLISH_PROFILE` | Web App → Overview → Download publish profile; paste the entire XML file |

Application runtime settings such as OCR keys, storage configuration, session
security, and the GitHub Models token remain in **Azure Web App → Environment
variables**. They are not build arguments and must never be committed.

## First run

1. Rotate any credential that has previously appeared in a local JSON file,
   terminal output, screenshot, or commit.
2. Add all variables and secrets above.
3. Open **Actions → Test and deploy → Run workflow** to test the configuration.
4. Later deployments happen automatically when a commit reaches `main`.

The Neon migration step runs `alembic upgrade head`. It changes the schema only;
it does not seed users, purge data, or deploy a PostgreSQL server.
