@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
setlocal

rem All messages here are ASCII on purpose: the .bat file itself may be read
rem by a cp950 console. Chinese text is printed by Python, which reconfigures
rem stdout/stderr to UTF-8 (see hkjobs/contract.py configure_io).

set "PY=python"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"

echo hk-job-scraper / guided mode
echo Python: %PY%
echo.

"%PY%" -c "import requests, bs4, lxml" >nul 2>&1
if not errorlevel 1 goto :ready

echo Project dependencies are missing (requests / beautifulsoup4 / lxml).
set /p "ANS=Install them now with pip? [Y/n] "
if /i "%ANS%"=="n" goto :end
"%PY%" -m pip install -r requirements.txt
if errorlevel 1 goto :fail

:ready
"%PY%" -m hkjobs guide
goto :end

:fail
echo Install failed. Run this manually: %PY% -m pip install -r requirements.txt

:end
echo.
echo Press any key to close this window.
pause >nul
endlocal
