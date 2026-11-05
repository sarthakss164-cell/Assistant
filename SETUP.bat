@echo off
setlocal enabledelayedexpansion

:: ============================================================================
:: LIGHT AI V1.0 — One-Click Automated Environment Setup
:: Prepares Python virtual environment (.venv), installs dependencies,
:: builds the Electron dashboard, checks external prerequisites,
:: and generates a desktop shortcut.
:: ============================================================================

title LIGHT AI V1.0 - Setup Wizard

:: Dynamically switch directory to the script root (handles paths with spaces)
cd /d "%~dp0"

set "SETUP_SCRIPT=%~dp0installer\setup_environment.ps1"

if not exist "%SETUP_SCRIPT%" (
    echo.
    echo ========================================================================
    echo  [FATAL ERROR] Setup script not found:
    echo  "%SETUP_SCRIPT%"
    echo ========================================================================
    echo.
    echo Please ensure the installer\setup_environment.ps1 file is present.
    echo Press any key to exit...
    pause >nul
    exit /b 1
)

:: Run the PowerShell setup wizard with ExecutionPolicy Bypass
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SETUP_SCRIPT%" %*
set SETUP_EXIT_CODE=%ERRORLEVEL%

if %SETUP_EXIT_CODE% neq 0 (
    echo.
    echo ========================================================================
    echo  [ERROR] LIGHT AI setup encountered an error (Exit code: %SETUP_EXIT_CODE%).
    echo ========================================================================
    echo.
    echo Please review the diagnostic messages above.
    echo Press any key to close this window...
    pause >nul
    exit /b %SETUP_EXIT_CODE%
)

exit /b 0

