@echo off
:: 1. Save current location and move to the venv Scripts folder
pushd "C:\Users\HiWi\Desktop\Terril\05_python_venv\Scripts"

:: 2. Activate the virtual environment
:: 'call' is required to run another batch file without ending this one
call activate.bat

:: 3. Return to the original directory
popd

:: cd bcm-pyqt
:: 4. Keep the CMD window open so you can use the activated venv
cmd /k

