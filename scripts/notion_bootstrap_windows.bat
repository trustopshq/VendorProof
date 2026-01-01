@echo off
setlocal

echo Notion Import Helper (Windows)
echo ---------------------------------
echo This helper opens the setup docs and runs a dry-run if Python is available.
echo.

where python >nul 2>&1
if %errorlevel% neq 0 (
  echo Python was not found on this machine.
  echo Please install Python 3.10+ and make sure it is added to PATH.
  echo Recommended: https://www.python.org/downloads/
  echo.
  echo After installing Python, run this file again.
  echo Opening docs...
  start "" "%~dp0..\docs\BOOTSTRAP.md"
  echo.
  pause
  exit /b 1
)

echo Python detected.
echo.
echo If this is your first run, install dependencies:
echo   python -m pip install -r requirements.txt
echo.
echo Running dry-run (import plan):
python "%~dp0notion_bootstrap.py"

if %errorlevel% neq 0 (
  echo.
  echo Dry-run failed. Review the error and fix it before applying.
  echo Opening docs...
  start "" "%~dp0..\docs\BOOTSTRAP.md"
  echo.
  pause
  exit /b 1
)

echo.
echo Next step (import):
echo   set NOTION_TOKEN=your_token
echo   python "%~dp0notion_bootstrap.py" --apply
echo.
echo Opening docs for full steps...
start "" "%~dp0..\docs\BOOTSTRAP.md"
pause
