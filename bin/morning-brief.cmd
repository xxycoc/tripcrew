@echo off
setlocal
cd /d "%~dp0.." || exit /b 1
if not exist "relay\.local" mkdir "relay\.local"
if errorlevel 1 exit /b 1
set "PYTHONPATH=%CD%\relay"
set "PYTHONUNBUFFERED=1"
set "PYTHONDONTWRITEBYTECODE=1"
"relay\.venv\Scripts\python.exe" -m relay --config "relay\relay.local.toml" post %* >> "relay\.local\brief.log" 2>&1
exit /b %errorlevel%
