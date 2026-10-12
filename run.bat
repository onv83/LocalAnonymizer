@echo off
setlocal
cd /d "%~dp0"
if exist "dist\LocalAnonymizer\LocalAnonymizer.exe" (
  start "" "dist\LocalAnonymizer\LocalAnonymizer.exe" %*
  exit /b 0
)
if not exist ".venv\Scripts\python.exe" (
  echo Сначала выполните: uv sync --extra dev --no-install-project
  exit /b 1
)
set "PYTHONPATH=%~dp0src"
".venv\Scripts\python.exe" -m local_anonymizer.app %*
