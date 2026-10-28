@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
%PY% --version >nul 2>nul || (echo Python is not installed. Install from https://www.python.org/downloads/ and tick "Add to PATH". & pause & exit /b 2)
%PY% -m pip install --quiet --disable-pip-version-check requests
for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set TODAY=%%d
%PY% fetch_prices.py "%~dp0downloads\%TODAY%" > "%~dp0last_run.log" 2>&1
type "%~dp0last_run.log"
if "%1"=="" pause
