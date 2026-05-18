@echo off
REM ====================================================================
REM  Build script - delegate to build_batch.py to safely handle Chinese
REM  exe name without cmd encoding issues (UTF-8 vs GBK).
REM ====================================================================
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.8+ and add to PATH.
    pause
    exit /b 1
)

python build_batch.py
if errorlevel 1 (
    pause
    exit /b 1
)

pause
