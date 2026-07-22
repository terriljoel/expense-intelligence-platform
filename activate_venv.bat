@echo off
set "VENV_ACTIVATE=%~dp0.venv\Scripts\activate.bat"

if not exist "%VENV_ACTIVATE%" (
    echo Virtual environment not found.
    echo Create it first with: python -m venv .venv
    exit /b 1
)

call "%VENV_ACTIVATE%"
