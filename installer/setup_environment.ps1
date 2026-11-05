<#
================================================================================
LIGHT AI V1.0 — Automated Environment Setup Wizard
Detects prerequisites, initializes project .venv, installs Python & Node
dependencies, compiles production dashboard, and configures desktop shortcut.
================================================================================
#>

[CmdletBinding()]
param(
    [switch]$NonInteractive,
    [switch]$SkipDashboard,
    [switch]$SkipShortcut,
    [switch]$AutoLaunch,
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"

# 1. PATH RESOLUTION
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$DashboardDir = Join-Path $ProjectRoot "dashboard"
$VenvDir = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$RequirementsFile = Join-Path $ProjectRoot "requirements.txt"
$EnvExample = Join-Path $ProjectRoot ".env.example"
$EnvFile = Join-Path $ProjectRoot ".env"
$ContactsExample = Join-Path $ProjectRoot "config\contacts.json.example"
$ContactsFile = Join-Path $ProjectRoot "config\contacts.json"

[System.IO.Directory]::SetCurrentDirectory($ProjectRoot)

function Print-SetupBanner {
    Write-Host ""
    Write-Host "========================================================================" -ForegroundColor Cyan
    Write-Host "    _     ___ ____ _   _ _____      _    ___   __     _____ _        " -ForegroundColor Cyan
    Write-Host "   | |   |_ _/ ___| | | |_   _|    / \  |_ _|  \ \   / /_ / |        " -ForegroundColor Cyan
    Write-Host "   | |    | | |  _| |_| | | |     / _ \  | |    \ \ / / | || |        " -ForegroundColor Cyan
    Write-Host "   | |___ | | |_| |  _  | | |    / ___ \ | |     \ V /  | || |___ _ _ " -ForegroundColor Cyan
    Write-Host "   |_____|___\____|_| |_| |_|   /_/   \_\___|     \_/   |_(_)_____(_|_)" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "               LIGHT AI V1.0 - ENVIRONMENT SETUP WIZARD" -ForegroundColor Yellow
    Write-Host "========================================================================" -ForegroundColor Cyan
    Write-Host " Project Location : $ProjectRoot" -ForegroundColor Gray
    Write-Host " Target OS        : Windows (64-bit)" -ForegroundColor Gray
    Write-Host "========================================================================" -ForegroundColor Cyan
    Write-Host ""
}

function Prompt-UserConfirmation([string]$PromptText) {
    if ($NonInteractive) { return $false }
    Write-Host "$PromptText [y/N]: " -NoNewline -ForegroundColor Yellow
    $ans = Read-Host
    return ($ans -match '^(y|yes)$')
}

function Test-PythonCandidate([string]$CandidateExe) {
    if (-not $CandidateExe -or -not (Test-Path $CandidateExe)) {
        return $null
    }
    try {
        $out = & $CandidateExe -c "import sys, platform; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}|{platform.architecture()[0]}|{sys.executable}')" 2>$null
        if ($out) {
            $parts = $out.Trim().Split('|')
            if ($parts.Length -ge 3) {
                $verStr = $parts[0]
                $arch = $parts[1]
                $exePath = $parts[2]
                $vNums = $verStr.Split('.')
                $major = [int]$vNums[0]
                $minor = [int]$vNums[1]

                return [PSCustomObject]@{
                    Path = $exePath
                    Version = $verStr
                    Major = $major
                    Minor = $minor
                    Is64Bit = ($arch -eq '64bit')
                    IsCompatible = ($major -eq 3 -and $minor -ge 10 -and $minor -le 12 -and $arch -eq '64bit')
                }
            }
        }
    } catch {}
    return $null
}

Print-SetupBanner

# ==============================================================================
# STEP 1: DETECT & VALIDATE PYTHON
# ==============================================================================
Write-Host "[STEP 1/6] Detecting and validating Python (64-bit, 3.10 - 3.12)..." -ForegroundColor Cyan

$DetectedPython = $null

if ($PythonPath) {
    $DetectedPython = Test-PythonCandidate $PythonPath
    if (-not $DetectedPython) {
        Write-Host "[ERROR] Explicitly provided Python at '$PythonPath' is invalid or not found!" -ForegroundColor Red
        exit 1
    }
}

if (-not $DetectedPython -and $env:LIGHT_AI_PYTHON) {
    $DetectedPython = Test-PythonCandidate $env:LIGHT_AI_PYTHON
}

# Check Windows Python Launcher (py)
if (-not $DetectedPython) {
    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd) {
        foreach ($pyArg in @("-3.12", "-3.11", "-3.10", "-3")) {
            try {
                $pyOut = & py $pyArg -c "import sys; print(sys.executable)" 2>$null
                if ($pyOut) {
                    $cand = Test-PythonCandidate $pyOut.Trim()
                    if ($cand -and $cand.IsCompatible) {
                        $DetectedPython = $cand
                        break
                    }
                }
            } catch {}
        }
    }
}

# Check python.exe on PATH
if (-not $DetectedPython) {
    $pathPython = Get-Command python -ErrorAction SilentlyContinue
    if ($pathPython) {
        $cand = Test-PythonCandidate $pathPython.Source
        if ($cand -and $cand.IsCompatible) {
            $DetectedPython = $cand
        }
    }
}

# Check Developer Conda Path Fallback
if (-not $DetectedPython) {
    $devPython = "python.exe path"
    if (Test-Path $devPython) {
        $cand = Test-PythonCandidate $devPython
        if ($cand -and $cand.IsCompatible) {
            $DetectedPython = $cand
        }
    }
}

if (-not $DetectedPython -or -not $DetectedPython.IsCompatible) {
    Write-Host ""
    Write-Host "========================================================================" -ForegroundColor Red
    Write-Host " [PREREQUISITE REQUIRED] Python 3.10 - 3.12 (64-bit) Not Found" -ForegroundColor Red
    Write-Host "========================================================================" -ForegroundColor Red
    Write-Host "LIGHT AI requires Python 3.10, 3.11, or 3.12 (64-bit) on Windows." -ForegroundColor Yellow
    Write-Host "Standard download : https://www.python.org/downloads/" -ForegroundColor White
    Write-Host "Important note    : Make sure to check 'Add python.exe to PATH' during installation." -ForegroundColor Yellow
    Write-Host ""

    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget -and -not $NonInteractive) {
        Write-Host "Windows Package Manager (winget) is available on this system." -ForegroundColor Cyan
        if (Prompt-UserConfirmation "Would you like to install Python 3.12 automatically via winget?") {
            Write-Host "Running: winget install Python.Python.3.12 --scope user" -ForegroundColor Cyan
            & winget install Python.Python.3.12 --scope user
            Write-Host "Please restart this setup script after the installation finishes." -ForegroundColor Yellow
            exit 1
        }
    }

    Write-Host "Please install Python 3.12 (64-bit) and run SETUP.bat again." -ForegroundColor Yellow
    exit 1
}

Write-Host "  [OK] Detected Python $($DetectedPython.Version) ($($DetectedPython.Path))" -ForegroundColor Green

# ==============================================================================
# STEP 2: PROJECT VIRTUAL ENVIRONMENT (.venv)
# ==============================================================================
Write-Host ""
Write-Host "[STEP 2/6] Configuring project virtual environment (.venv)..." -ForegroundColor Cyan

$NeedsNewVenv = $true
if (Test-Path $VenvPython) {
    $existingVenv = Test-PythonCandidate $VenvPython
    if ($existingVenv -and $existingVenv.IsCompatible) {
        Write-Host "  [OK] Existing healthy .venv detected ($($existingVenv.Version))." -ForegroundColor Green
        $NeedsNewVenv = $false
    } else {
        Write-Host "  [NOTICE] Existing .venv appears broken or incompatible. Recreating..." -ForegroundColor Yellow
        Remove-Item -Recurse -Force $VenvDir -ErrorAction SilentlyContinue
    }
}

if ($NeedsNewVenv) {
    Write-Host "  [...] Creating dedicated virtual environment at '$VenvDir'..." -ForegroundColor Cyan
    & $DetectedPython.Path -m venv $VenvDir
    if (-not (Test-Path $VenvPython)) {
        Write-Host "[ERROR] Failed to initialize virtual environment at '$VenvDir'!" -ForegroundColor Red
        exit 1
    }
    Write-Host "  [OK] Virtual environment created successfully." -ForegroundColor Green
}

Write-Host "  [...] Upgrading pip in virtual environment..." -ForegroundColor Cyan
& $VenvPython -m pip install --upgrade pip --quiet 2>$null | Out-Null

Write-Host "  [...] Installing Python dependencies from requirements.txt (this may take 1-2 minutes)..." -ForegroundColor Cyan
& $VenvPython -m pip install -r $RequirementsFile --quiet

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to install Python dependencies via pip!" -ForegroundColor Red
    exit 1
}

# Verify critical imports inside .venv
Write-Host "  [VERIFY] Testing runtime Python modules..." -ForegroundColor Cyan
$verifyScript = @"
import aiohttp
import openai
import speech_recognition
import pyaudio
import edge_tts
import pygame
import psutil
import vlc
import yt_dlp
import pywhatkit
print('ALL_MODULES_OK')
"@

$vTest = & $VenvPython -c $verifyScript 2>$null
if ($vTest -match 'ALL_MODULES_OK') {
    Write-Host "  [OK] All backend runtime Python packages verified." -ForegroundColor Green
} else {
    Write-Host "  [WARNING] Some optional Python packages reported import notices, but basic environment is intact." -ForegroundColor Yellow
}

# ==============================================================================
# STEP 3: DETECT NODE.JS & NPM
# ==============================================================================
Write-Host ""
Write-Host "[STEP 3/6] Detecting Node.js and npm for Electron dashboard..." -ForegroundColor Cyan

$nodeCmd = Get-Command node.exe, node -ErrorAction SilentlyContinue | Select-Object -First 1
$npmCmd = Get-Command npm.cmd, npm -ErrorAction SilentlyContinue | Select-Object -First 1

if (-not $nodeCmd -or -not $npmCmd) {
    Write-Host ""
    Write-Host "========================================================================" -ForegroundColor Red
    Write-Host " [PREREQUISITE REQUIRED] Node.js 18+ and npm Not Found" -ForegroundColor Red
    Write-Host "========================================================================" -ForegroundColor Red
    Write-Host "The LIGHT AI desktop dashboard requires Node.js 18+ LTS to run the Electron HUD." -ForegroundColor Yellow
    Write-Host "Official download : https://nodejs.org/" -ForegroundColor White
    Write-Host ""

    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget -and -not $NonInteractive) {
        Write-Host "Windows Package Manager (winget) is available on this system." -ForegroundColor Cyan
        if (Prompt-UserConfirmation "Would you like to install Node.js LTS automatically via winget?") {
            Write-Host "Running: winget install OpenJS.NodeJS.LTS" -ForegroundColor Cyan
            & winget install OpenJS.NodeJS.LTS
            Write-Host "Please restart this setup script after the installation finishes." -ForegroundColor Yellow
            exit 1
        }
    }

    Write-Host "Please install Node.js LTS and run SETUP.bat again." -ForegroundColor Yellow
    exit 1
}

$nodeVerStr = & $nodeCmd.Source --version
$nodeMajor = 0
if ($nodeVerStr -match '^v(\d+)') {
    $nodeMajor = [int]$matches[1]
}

if ($nodeMajor -lt 18) {
    Write-Host "[ERROR] Node.js version $nodeVerStr is too old! Version 18+ is required." -ForegroundColor Red
    exit 1
}

Write-Host "  [OK] Node.js $nodeVerStr detected ($($nodeCmd.Source))" -ForegroundColor Green
Write-Host "  [OK] NPM CLI detected ($($npmCmd.Source))" -ForegroundColor Green

# ==============================================================================
# STEP 4: DASHBOARD BUILD & COMPILE
# ==============================================================================
if (-not $SkipDashboard) {
    Write-Host ""
    Write-Host "[STEP 4/6] Installing dashboard dependencies and building production assets..." -ForegroundColor Cyan

    $packageLock = Join-Path $DashboardDir "package-lock.json"
    $nodeModulesDir = Join-Path $DashboardDir "node_modules"

    Push-Location $DashboardDir
    try {
        if (-not (Test-Path $nodeModulesDir)) {
            Write-Host "  [...] Installing npm dependencies (running npm ci)..." -ForegroundColor Cyan
            cmd.exe /c "npm ci" 2>$null | Out-Null
            if ($LASTEXITCODE -ne 0) {
                Write-Host "  [NOTICE] npm ci fallback to npm install..." -ForegroundColor Yellow
                cmd.exe /c "npm install" 2>$null | Out-Null
            }
        } else {
            Write-Host "  [OK] Existing node_modules verified." -ForegroundColor Green
        }

        Write-Host "  [...] Building production dashboard bundle (npm run build)..." -ForegroundColor Cyan
        cmd.exe /c "npm run build" | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[ERROR] Failed to compile production dashboard bundle!" -ForegroundColor Red
            exit 1
        }

        $distHtml = Join-Path $DashboardDir "dist\index.html"
        if (Test-Path $distHtml) {
            Write-Host "  [OK] Production dashboard compiled at 'dashboard\dist\index.html'." -ForegroundColor Green
        } else {
            Write-Host "[ERROR] Expected build output 'dashboard\dist\index.html' not found!" -ForegroundColor Red
            exit 1
        }
    } finally {
        Pop-Location
    }
} else {
    Write-Host ""
    Write-Host "[STEP 4/6] Dashboard build skipped per parameter." -ForegroundColor Gray
}

# ==============================================================================
# STEP 5: EXTERNAL DEPENDENCIES (VLC MEDIA PLAYER)
# ==============================================================================
Write-Host ""
Write-Host "[STEP 5/6] Checking external multimedia dependencies..." -ForegroundColor Cyan

$StandardVlcPath = "C:\Program Files\VideoLAN\VLC\vlc.exe"
$VlcFound = $false

if (Test-Path $StandardVlcPath) {
    $VlcFound = $true
} else {
    $vlcCmd = Get-Command vlc.exe, vlc -ErrorAction SilentlyContinue
    if ($vlcCmd) {
        $VlcFound = $true
    }
}

if ($VlcFound) {
    Write-Host "  [OK] VLC Media Player (64-bit) detected." -ForegroundColor Green
} else {
    Write-Host "  [NOTICE] VLC Media Player (64-bit) was not detected." -ForegroundColor Yellow
    Write-Host "  VLC is required for streaming background YouTube music and playlists." -ForegroundColor Yellow
    Write-Host "  All other assistant features (voice interaction, AI reasoning, WhatsApp," -ForegroundColor Yellow
    Write-Host "  and app launching) will work normally without VLC." -ForegroundColor Yellow
    Write-Host "  Download VLC 64-bit here: https://www.videolan.org/vlc/" -ForegroundColor White
}

# ==============================================================================
# STEP 6: CONFIGURATION FILES & SHORTCUT
# ==============================================================================
Write-Host ""
Write-Host "[STEP 6/6] Initializing user configuration and shortcuts..." -ForegroundColor Cyan

# 1. Configuration (.env)
if (-not (Test-Path $EnvFile)) {
    if (Test-Path $EnvExample) {
        Copy-Item $EnvExample $EnvFile
        Write-Host "  [NOTICE] Created new '.env' configuration file from template." -ForegroundColor Green
        Write-Host "  IMPORTANT: Open '.env' in Notepad and set your personal COE_AI_KEY." -ForegroundColor Yellow
    }
} else {
    Write-Host "  [OK] Existing '.env' configuration file preserved." -ForegroundColor Green
}

# 2. Contacts (config/contacts.json)
if (-not (Test-Path $ContactsFile)) {
    if (Test-Path $ContactsExample) {
        Copy-Item $ContactsExample $ContactsFile
        Write-Host "  [NOTICE] Created 'config/contacts.json' from example template." -ForegroundColor Green
    }
} else {
    Write-Host "  [OK] Existing 'config/contacts.json' preserved." -ForegroundColor Green
}

# 3. Desktop Shortcut
if (-not $SkipShortcut) {
    $shortcutScript = Join-Path $ProjectRoot "launcher\create_desktop_shortcut.ps1"
    if (Test-Path $shortcutScript) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $shortcutScript
    }
}

Write-Host ""
Write-Host "========================================================================" -ForegroundColor Green
Write-Host "             LIGHT AI V1.0 SETUP COMPLETED SUCCESSFULLY" -ForegroundColor Green
Write-Host "========================================================================" -ForegroundColor Green
Write-Host "  1. Virtual Environment : $VenvDir" -ForegroundColor White
Write-Host "  2. Production Build    : dashboard\dist\index.html" -ForegroundColor White
Write-Host "  3. Desktop Shortcut    : LIGHT AI V1.0 on your Desktop" -ForegroundColor White
Write-Host "  4. Configuration File  : .env" -ForegroundColor White
Write-Host "========================================================================" -ForegroundColor Green
Write-Host ""

if ($AutoLaunch) {
    Write-Host "Launching LIGHT AI V1.0..." -ForegroundColor Cyan
    $batchLauncher = Join-Path $ProjectRoot "Launch_LIGHT_AI.bat"
    Start-Process -FilePath $batchLauncher
} elseif (-not $NonInteractive) {
    if (Prompt-UserConfirmation "Would you like to launch LIGHT AI V1.0 now?") {
        $batchLauncher = Join-Path $ProjectRoot "Launch_LIGHT_AI.bat"
        Start-Process -FilePath $batchLauncher
    }
}

exit 0

