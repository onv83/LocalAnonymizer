@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pyinstaller.exe" (
  echo Выполните: uv sync --extra dev --no-install-project
  exit /b 1
)
set "STAGE=build\pyinstaller-output"
set "PROVENANCE=src\local_anonymizer\_build_provenance.py"
set "STAGE_MANIFEST=%STAGE%\LocalAnonymizer.manifest.json"
if exist "%STAGE%" rmdir /s /q "%STAGE%"
if errorlevel 1 exit /b %errorlevel%
if exist "%PROVENANCE%" del /q "%PROVENANCE%"
".venv\Scripts\python.exe" scripts\build_provenance.py "%PROVENANCE%"
if errorlevel 1 exit /b %errorlevel%
".venv\Scripts\pyinstaller.exe" --noconfirm --clean --workpath "build\pyinstaller-current" --distpath "build\pyinstaller-output" LocalAnonymizer.spec
set "BUILD_RC=%ERRORLEVEL%"
if exist "%PROVENANCE%" del /q "%PROVENANCE%"
if not "%BUILD_RC%"=="0" exit /b %BUILD_RC%
".venv\Scripts\python.exe" scripts\verify_packaged.py "%STAGE%\LocalAnonymizer\LocalAnonymizer.exe" --write-manifest "%STAGE_MANIFEST%"
if errorlevel 1 exit /b %errorlevel%
if exist "dist\LocalAnonymizer" rmdir /s /q "dist\LocalAnonymizer"
if errorlevel 1 exit /b %errorlevel%
if exist "dist\LocalAnonymizer.manifest.json" del /q "dist\LocalAnonymizer.manifest.json"
if not exist "dist" mkdir "dist"
move /y "%STAGE%\LocalAnonymizer" "dist\LocalAnonymizer" >nul
if errorlevel 1 exit /b %errorlevel%
move /y "%STAGE_MANIFEST%" "dist\LocalAnonymizer.manifest.json" >nul
if errorlevel 1 exit /b %errorlevel%
if exist "%STAGE%" rmdir /s /q "%STAGE%"
".venv\Scripts\python.exe" scripts\verify_packaged.py "dist\LocalAnonymizer\LocalAnonymizer.exe" --manifest "dist\LocalAnonymizer.manifest.json"
if errorlevel 1 exit /b %errorlevel%
echo Сборка: %CD%\dist\LocalAnonymizer\LocalAnonymizer.exe
