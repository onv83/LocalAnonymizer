@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pyinstaller.exe" (
  echo Выполните: uv sync --extra dev --no-install-project
  exit /b 1
)
".venv\Scripts\pyinstaller.exe" --noconfirm --clean LocalAnonymizer.spec
if errorlevel 1 exit /b %errorlevel%
echo Сборка: %CD%\dist\LocalAnonymizer\LocalAnonymizer.exe
