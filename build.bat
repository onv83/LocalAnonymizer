@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pyinstaller.exe" (
  echo Выполните: uv sync --extra dev --no-install-project
  exit /b 1
)
set "STAGE=build\pyinstaller-output"
if exist "%STAGE%" rmdir /s /q "%STAGE%"
if errorlevel 1 exit /b %errorlevel%
".venv\Scripts\pyinstaller.exe" --noconfirm --clean --workpath "build\pyinstaller-current" --distpath "build\pyinstaller-output" LocalAnonymizer.spec
if errorlevel 1 exit /b %errorlevel%
".venv\Scripts\python.exe" scripts\verify_packaged.py "%STAGE%\LocalAnonymizer\LocalAnonymizer.exe"
if errorlevel 1 exit /b %errorlevel%
if exist "dist\LocalAnonymizer" rmdir /s /q "dist\LocalAnonymizer"
if errorlevel 1 exit /b %errorlevel%
if not exist "dist" mkdir "dist"
move /y "%STAGE%\LocalAnonymizer" "dist\LocalAnonymizer" >nul
if errorlevel 1 exit /b %errorlevel%
if exist "%STAGE%" rmdir /s /q "%STAGE%"
".venv\Scripts\python.exe" scripts\verify_packaged.py "dist\LocalAnonymizer\LocalAnonymizer.exe"
if errorlevel 1 exit /b %errorlevel%
echo Сборка: %CD%\dist\LocalAnonymizer\LocalAnonymizer.exe
