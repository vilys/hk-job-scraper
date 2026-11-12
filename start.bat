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

rem Check the interpreter itself BEFORE blaming dependencies. Without this,
rem a missing python.exe fails the import check below and the launcher wrongly
rem reports "dependencies are missing" and then "Install failed".
"%PY%" --version >nul 2>&1
if errorlevel 1 goto :nopython

"%PY%" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto :oldpython

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

:nopython
echo Python 3.10+ was not found, or could not start.
echo Please install Python 3.10+ from https://www.python.org/downloads/
echo During setup, tick "Add python.exe to PATH", then reopen this window.
echo If the Microsoft Store opened instead, that is only a Windows app alias:
echo install the real Python from python.org (or switch the alias off).
echo Looking for: %PY%
goto :end

:oldpython
echo This project needs Python 3.10 or newer; the interpreter found did not
echo pass the version check (it may be too old, or only a Store alias).
echo Please install Python 3.10+ from https://www.python.org/downloads/
echo and tick "Add python.exe to PATH" during setup.
echo Looking for: %PY%
goto :end

:fail
echo Install failed. Run this manually: %PY% -m pip install -r requirements.txt

:end
echo.
echo Press any key to close this window.
pause >nul
endlocal
