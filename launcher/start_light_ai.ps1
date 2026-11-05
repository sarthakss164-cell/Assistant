<#
================================================================================
LIGHT AI V1.0 — Unified Desktop Launcher Orchestrator
Deterministically starts and manages Python backend + Electron/React Dashboard.
================================================================================
#>

[CmdletBinding()]
param(
    [switch]$BackendOnly,
    [switch]$DashboardOnly,
    [switch]$ShowDashboardConsole,
    [string]$PythonPath = "",
    [int]$BackendTimeoutSeconds = 30
)

$ErrorActionPreference = "Stop"

# 1. DYNAMIC PATH RESOLUTION
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$DashboardDir = Join-Path $ProjectRoot "dashboard"
$MainPy = Join-Path $ProjectRoot "main.py"
$PackageJson = Join-Path $DashboardDir "package.json"
$NodeModules = Join-Path $DashboardDir "node_modules"

# Set current process working directory to ProjectRoot
[System.IO.Directory]::SetCurrentDirectory($ProjectRoot)

function Print-Banner {
    Write-Host ""
    Write-Host "========================================================================" -ForegroundColor Cyan
    Write-Host "    _     ___ ____ _   _ _____      _    ___   __     _____ _        " -ForegroundColor Cyan
    Write-Host "   | |   |_ _/ ___| | | |_   _|    / \  |_ _|  \ \   / /_ / |        " -ForegroundColor Cyan
    Write-Host "   | |    | | |  _| |_| | | |     / _ \  | |    \ \ / / | || |        " -ForegroundColor Cyan
    Write-Host "   | |___ | | |_| |  _  | | |    / ___ \ | |     \ V /  | || |___ _ _ " -ForegroundColor Cyan
    Write-Host "   |_____|___\____|_| |_| |_|   /_/   \_\___|     \_/   |_(_)_____(_|_)" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "                  LIGHT AI V1.0 - DESKTOP LAUNCHER" -ForegroundColor Yellow
    Write-Host "========================================================================" -ForegroundColor Cyan
    Write-Host " Project Root : $ProjectRoot" -ForegroundColor Gray
    Write-Host " Timestamp    : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Gray
    Write-Host "========================================================================" -ForegroundColor Cyan
    Write-Host ""
}

function Test-PortListening([string]$HostAddress, [int]$Port) {
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $connectTask = $tcp.ConnectAsync($HostAddress, $Port)
        $waited = $connectTask.Wait(800)
        if ($waited -and $tcp.Connected) {
            $tcp.Close()
            return $true
        }
        $tcp.Close()
        return $false
    } catch {
        return $false
    }
}

function Stop-TargetProcessTree([System.Diagnostics.Process]$Proc, [string]$Name) {
    if ($null -eq $Proc) { return }
    try {
        if (-not $Proc.HasExited) {
            Write-Host "[CLEANUP] Stopping $Name (PID: $($Proc.Id))..." -ForegroundColor Yellow
            try { $Proc.Kill() } catch {}
            # Clean up process tree targeting strictly this PID
            taskkill.exe /PID $Proc.Id /T /F 2>$null | Out-Null
        }
    } catch {
        # Already exited
    }
}

Print-Banner

# 2. RESOLVE PYTHON INTERPRETER
$ResolvedPython = ""
if ($PythonPath) {
    if (Test-Path $PythonPath) {
        $ResolvedPython = $PythonPath
    } else {
        Write-Host "[ERROR] Explicitly specified Python interpreter not found at '$PythonPath'!" -ForegroundColor Red
        exit 1
    }
} elseif ($env:LIGHT_AI_PYTHON) {
    if (Test-Path $env:LIGHT_AI_PYTHON) {
        $ResolvedPython = $env:LIGHT_AI_PYTHON
    } else {
        Write-Host "[ERROR] Python interpreter in LIGHT_AI_PYTHON environment variable not found at '$env:LIGHT_AI_PYTHON'!" -ForegroundColor Red
        exit 1
    }
} else {
    # 1. Project-local virtual environment (created by SETUP.bat)
    $LocalVenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path $LocalVenvPython) {
        $ResolvedPython = $LocalVenvPython
    } else {
        # 2. Windows Python Launcher (py -3.12 / py -3)
        $pyCmd = Get-Command py -ErrorAction SilentlyContinue
        if ($pyCmd) {
            try {
                $pyOut = & py -3.12 -c "import sys; print(sys.executable)" 2>$null
                if ($pyOut -and (Test-Path $pyOut.Trim())) {
                    $ResolvedPython = $pyOut.Trim()
                }
            } catch {}
            if (-not $ResolvedPython) {
                try {
                    $pyOut = & py -3 -c "import sys; print(sys.executable)" 2>$null
                    if ($pyOut -and (Test-Path $pyOut.Trim())) {
                        $ResolvedPython = $pyOut.Trim()
                    }
                } catch {}
            }
        }

        # 3. Standard python on PATH
        if (-not $ResolvedPython) {
            $cmdPython = Get-Command python -ErrorAction SilentlyContinue
            if ($cmdPython -and (Test-Path $cmdPython.Source)) {
                $ResolvedPython = $cmdPython.Source
            }
        }

        # 4. Developer fallback environment
        if (-not $ResolvedPython) {
            $DefaultCondaPython = "python.exe path"
            if (Test-Path $DefaultCondaPython) {
                $ResolvedPython = $DefaultCondaPython
            }
        }
    }
}

# 3. PRE-FLIGHT VALIDATIONS
Write-Host "[PRE-FLIGHT] Checking prerequisites..." -ForegroundColor Cyan

if (-not $DashboardOnly) {
    if (-not $ResolvedPython -or -not (Test-Path $ResolvedPython)) {
        Write-Host "[ERROR] No compatible Python interpreter was detected!" -ForegroundColor Red
        Write-Host "Please run 'SETUP.bat' first to automatically install and configure LIGHT AI." -ForegroundColor Yellow
        Write-Host "Alternatively, set the LIGHT_AI_PYTHON environment variable pointing to python.exe." -ForegroundColor Yellow
        exit 1
    }
    Write-Host "  [OK] Python interpreter : $ResolvedPython" -ForegroundColor Green

    if (-not (Test-Path $MainPy)) {
        Write-Host "[ERROR] Entrypoint '$MainPy' does not exist!" -ForegroundColor Red
        exit 1
    }
    Write-Host "  [OK] Backend entrypoint : $MainPy" -ForegroundColor Green
}

if (-not $BackendOnly) {
    if (-not (Test-Path $DashboardDir)) {
        Write-Host "[ERROR] Dashboard directory not found at '$DashboardDir'!" -ForegroundColor Red
        exit 1
    }
    if (-not (Test-Path $PackageJson)) {
        Write-Host "[ERROR] package.json not found in '$DashboardDir'!" -ForegroundColor Red
        exit 1
    }
    Write-Host "  [OK] Dashboard manifest : $PackageJson" -ForegroundColor Green

    if (-not (Test-Path $NodeModules)) {
        Write-Host "[ERROR] Dashboard node_modules not found in '$DashboardDir'!" -ForegroundColor Red
        Write-Host "Please open a terminal in '$DashboardDir' and run 'npm install' first." -ForegroundColor Yellow
        exit 1
    }
    Write-Host "  [OK] Node dependencies  : $NodeModules" -ForegroundColor Green

    $npmCmd = Get-Command npm.cmd, npm -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $npmCmd) {
        Write-Host "[ERROR] Node.js package manager 'npm' was not found in PATH!" -ForegroundColor Red
        exit 1
    }
    Write-Host "  [OK] NPM CLI executable : $($npmCmd.Source)" -ForegroundColor Green
}

# 4. DUPLICATE INSTANCE DETECTION (Port 8765)
if (-not $DashboardOnly) {
    Write-Host "[PRE-FLIGHT] Checking for duplicate instances..." -ForegroundColor Cyan
    if (Test-PortListening "127.0.0.1" 8765) {
        Write-Host ""
        Write-Host "[ERROR] LIGHT AI backend is already running (Port 8765 is active)!" -ForegroundColor Red
        Write-Host "Only one instance of LIGHT AI can run at a time to prevent port collisions." -ForegroundColor Yellow
        Write-Host "Please close the running LIGHT AI dashboard or console before starting a new one." -ForegroundColor Yellow
        Write-Host ""
        exit 1
    }
    Write-Host "  [OK] Port 8765 is available." -ForegroundColor Green
}

Write-Host ""

# 5. STARTUP ORCHESTRATION
$BackendProcess = $null
$DashboardProcess = $null

try {
    # Step A: Launch Backend
    if (-not $DashboardOnly) {
        Write-Host "[1/3] Starting LIGHT AI Python backend..." -ForegroundColor Cyan
        
        # Start Python backend with clean arguments
        $BackendProcess = Start-Process -FilePath $ResolvedPython `
            -ArgumentList "main.py" `
            -WorkingDirectory $ProjectRoot `
            -PassThru

        if ($null -eq $BackendProcess) {
            Write-Host "[ERROR] Failed to start Python backend process!" -ForegroundColor Red
            exit 1
        }
        Write-Host "  [OK] Backend process spawned (PID: $($BackendProcess.Id))." -ForegroundColor Green

        # Step B: Deterministic TCP Readiness Probe on Port 8765
        Write-Host "[2/3] Waiting for WebSocket bridge on 127.0.0.1:8765..." -ForegroundColor Cyan
        $elapsed = 0.0
        $ready = $false
        $pollInterval = 0.5

        while ($elapsed -lt $BackendTimeoutSeconds) {
            if ($BackendProcess.HasExited) {
                Write-Host ""
                Write-Host "[ERROR] Backend process terminated unexpectedly during startup with exit code $($BackendProcess.ExitCode)!" -ForegroundColor Red
                exit 1
            }

            if (Test-PortListening "127.0.0.1" 8765) {
                $ready = $true
                break
            }

            Start-Sleep -Milliseconds ([int]($pollInterval * 1000))
            $elapsed += $pollInterval
        }

        if (-not $ready) {
            Write-Host ""
            Write-Host "[ERROR] Backend did not open port 8765 within $BackendTimeoutSeconds seconds!" -ForegroundColor Red
            exit 1
        }
        Write-Host "  [OK] WebSocket bridge active and accepting connections at ws://127.0.0.1:8765/ws." -ForegroundColor Green
    }

    # Step C: Launch Dashboard
    if (-not $BackendOnly) {
        Write-Host "[3/3] Starting Electron + React dashboard..." -ForegroundColor Cyan
        
        $npmRunScript = "electron:dev"
        if (Test-Path (Join-Path $DashboardDir "dist\index.html")) {
            $npmRunScript = "electron:prod"
            Write-Host "  [MODE] Loading precompiled production dashboard (dist/index.html)." -ForegroundColor Gray
        } else {
            Write-Host "  [MODE] Production build not found; falling back to Vite dev server." -ForegroundColor Yellow
        }

        $windowStyle = if ($ShowDashboardConsole) { "Normal" } else { "Minimized" }
        $DashboardProcess = Start-Process -FilePath "cmd.exe" `
            -ArgumentList "/c npm run $npmRunScript" `
            -WorkingDirectory $DashboardDir `
            -WindowStyle $windowStyle `
            -PassThru

        if ($null -eq $DashboardProcess) {
            Write-Host "[ERROR] Failed to spawn dashboard process!" -ForegroundColor Red
            exit 1
        }
        Write-Host "  [OK] Dashboard process spawned (PID: $($DashboardProcess.Id))." -ForegroundColor Green
    }

    # Step D: Unified Runtime Monitoring
    Write-Host ""
    Write-Host "========================================================================" -ForegroundColor Green
    Write-Host "                LIGHT AI V1.0 IS FULLY OPERATIONAL" -ForegroundColor Green
    Write-Host "========================================================================" -ForegroundColor Green
    if ($BackendProcess) {
        Write-Host " Backend PID      : $($BackendProcess.Id)" -ForegroundColor White
        Write-Host " WebSocket URL    : ws://127.0.0.1:8765/ws" -ForegroundColor White
    }
    if ($DashboardProcess) {
        Write-Host " Dashboard PID    : $($DashboardProcess.Id)" -ForegroundColor White
    }
    Write-Host " Instructions     : Close the Electron dashboard window or press Ctrl+C" -ForegroundColor Yellow
    Write-Host "                    in this launcher console to terminate all processes." -ForegroundColor Yellow
    Write-Host "========================================================================" -ForegroundColor Green
    Write-Host ""

    # Monitor loop
    while ($true) {
        Start-Sleep -Seconds 1

        # Check if Dashboard exited (e.g. user closed Electron window)
        if ($DashboardProcess -and $DashboardProcess.HasExited) {
            Write-Host "[INFO] Dashboard window closed by user. Initiating clean shutdown..." -ForegroundColor Cyan
            break
        }

        # Check if Backend exited (e.g. user said 'Light, shutdown')
        if ($BackendProcess -and $BackendProcess.HasExited) {
            Write-Host "[INFO] Assistant backend has completed execution. Closing dashboard..." -ForegroundColor Cyan
            break
        }
    }
}
finally {
    # CLEANUP: Target strictly processes spawned by this launcher
    Write-Host ""
    Write-Host "[CLEANUP] Stopping LIGHT AI session..." -ForegroundColor Yellow

    if ($DashboardProcess) {
        Stop-TargetProcessTree $DashboardProcess "Dashboard"
    }

    if ($BackendProcess) {
        Stop-TargetProcessTree $BackendProcess "Backend"
    }

    # Verify Port 8765 release
    Start-Sleep -Milliseconds 500
    if (Test-PortListening "127.0.0.1" 8765) {
        Write-Host "[CLEANUP] Port 8765 is still in use, ensuring release..." -ForegroundColor Yellow
        $conns = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
        foreach ($c in $conns) {
            if ($c.OwningProcess -and $c.OwningProcess -ne 0) {
                taskkill.exe /PID $c.OwningProcess /T /F 2>$null | Out-Null
            }
        }
    }

    Write-Host "[OK] LIGHT AI shutdown complete." -ForegroundColor Green
    Write-Host "========================================================================" -ForegroundColor Cyan
}

exit 0
