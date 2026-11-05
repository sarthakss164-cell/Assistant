@echo off
setlocal enabledelayedexpansion

:: ============================================================================
:: LIGHT AI V1.0 — Unified One-Click Desktop Launcher
:: Double-click this file to launch the Python assistant backend and Electron HUD.
:: ============================================================================

title LIGHT AI V1.0 - Desktop Launcher

:: Dynamically switch directory to the script root (handles paths with spaces)
cd /d "%~dp0"

set "LAUNCHER_SCRIPT=%~dp0launcher\start_light_ai.ps1"

if not exist "%LAUNCHER_SCRIPT%" (
    echo.
    echo ========================================================================
    echo  [FATAL ERROR] Launcher script not found:
    echo  "%LAUNCHER_SCRIPT%"
    echo ========================================================================
    echo.
    echo Please ensure the launcher\start_light_ai.ps1 file is present.
    echo Press any key to exit...
    pause >nul
    exit /b 1
)

:: Run the PowerShell orchestrator with ExecutionPolicy Bypass
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%LAUNCHER_SCRIPT%" %*
set LAUNCHER_EXIT_CODE=%ERRORLEVEL%

:: If an error occurred, pause so the user can read diagnostic information
if %LAUNCHER_EXIT_CODE% neq 0 (
    echo.
    echo ========================================================================
    echo  [ERROR] LIGHT AI launcher exited with code %LAUNCHER_EXIT_CODE%.
    echo ========================================================================
    echo.
    echo Press any key to close this window...
    pause >nul
    exit /b %LAUNCHER_EXIT_CODE%
)

exit /b 0

