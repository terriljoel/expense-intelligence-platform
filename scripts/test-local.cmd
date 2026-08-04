@echo off
setlocal

set "TEST_CONTAINER=expense-intelligence-ci"
set "DATABASE_URL=postgresql+psycopg://expense_test:expense_test@localhost:54329/expense_test"

docker info >nul 2>&1
if errorlevel 1 (
  echo ERROR: Start Docker Desktop and wait until the engine is running.
  exit /b 1
)

python -c "import alembic, fastapi, pytest" >nul 2>&1
if errorlevel 1 (
  echo ERROR: Activate the project Python environment before running this script.
  exit /b 1
)

docker rm -f "%TEST_CONTAINER%" >nul 2>&1
docker run --name "%TEST_CONTAINER%" -e POSTGRES_DB=expense_test -e POSTGRES_USER=expense_test -e POSTGRES_PASSWORD=expense_test -p 54329:5432 -d postgres:16-alpine >nul
if errorlevel 1 exit /b 1

echo Waiting for PostgreSQL...
for /L %%i in (1,1,30) do (
  docker exec "%TEST_CONTAINER%" pg_isready -U expense_test -d expense_test >nul 2>&1 && goto database_ready
  ping 127.0.0.1 -n 2 >nul
)
echo ERROR: PostgreSQL did not become ready.
set "RESULT=1"
goto cleanup

:database_ready
pushd apps\api
python -m alembic upgrade head || goto failed
python -m app.db.seed || goto failed
python -m ruff check . || goto failed
python -m pytest -q || goto failed
popd
docker build --file apps/api/Dockerfile --tag expense-intelligence:test . || goto failed_root
set "RESULT=0"
goto cleanup

:failed
set "RESULT=1"
popd
goto cleanup

:failed_root
set "RESULT=1"

:cleanup
docker rm -f "%TEST_CONTAINER%" >nul 2>&1
if "%RESULT%"=="0" echo All local checks passed.
exit /b %RESULT%
