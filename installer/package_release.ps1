<#
================================================================================
LIGHT AI V1.0 — Smart Distribution Packaging Script
Prepares clean distribution staging, executes pre-flight security & privacy
audit, and generates release ZIP package at dist/LIGHT_AI_V1.0_Windows.zip.
================================================================================
#>

[CmdletBinding()]
param(
    [string]$OutputPath = "",
    [switch]$SkipZipCompression
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$DistDir = Join-Path $ProjectRoot "dist"
$StagingRoot = Join-Path $DistDir "staging"
$StagingDir = Join-Path $StagingRoot "LIGHT_AI_V1.0_Windows"

if (-not $OutputPath) {
    $OutputPath = Join-Path $DistDir "LIGHT_AI_V1.0_Windows.zip"
}

Write-Host ""
Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "        LIGHT AI V1.0 - RELEASE DISTRIBUTION PACKAGER" -ForegroundColor Yellow
Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host " Project Root : $ProjectRoot" -ForegroundColor Gray
Write-Host " Output ZIP   : $OutputPath" -ForegroundColor Gray
Write-Host " Staging Dir  : $StagingDir" -ForegroundColor Gray
Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host ""

# Ensure target directories exist and clean any prior staging
if (Test-Path $StagingRoot) {
    Remove-Item -Recurse -Force $StagingRoot -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Path $StagingDir -Force | Out-Null
New-Item -ItemType Directory -Path $DistDir -Force | Out-Null

# ------------------------------------------------------------------------------
# 1. COPY ESSENTIAL RUNTIME SOURCE CODE & MANIFESTS
# ------------------------------------------------------------------------------
Write-Host "[1/4] Staging distribution files..." -ForegroundColor Cyan

# Root files
$RootFiles = @(
    "Launch_LIGHT_AI.bat",
    "SETUP.bat",
    "README_INSTALLATION.md",
    ".env.example",
    "requirements.txt",
    "requirements_runtime.txt",
    "main.py",
    "README.md"
)

foreach ($rf in $RootFiles) {
    $src = Join-Path $ProjectRoot $rf
    if (Test-Path $src) {
        Copy-Item $src (Join-Path $StagingDir $rf) -Force
    } else {
        Write-Host "  [WARNING] Root file '$rf' not found at '$src'!" -ForegroundColor Yellow
    }
}

# Python subsystem directories (excluding __pycache__)
$PyDirs = @("actions", "core", "memory", "speech", "utils", "launcher")
foreach ($d in $PyDirs) {
    $srcDir = Join-Path $ProjectRoot $d
    $destDir = Join-Path $StagingDir $d
    if (Test-Path $srcDir) {
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
        Get-ChildItem -Path $srcDir -Recurse -File | Where-Object { $_.FullName -notmatch '__pycache__' -and $_.Extension -ne '.pyc' } | ForEach-Object {
            $rel = $_.FullName.Substring($srcDir.Length).TrimStart('\', '/')
            $targetFile = Join-Path $destDir $rel
            $targetParent = Split-Path -Parent $targetFile
            if (-not (Test-Path $targetParent)) {
                New-Item -ItemType Directory -Path $targetParent -Force | Out-Null
            }
            Copy-Item $_.FullName $targetFile -Force
        }
    }
}

# Config directory (carefully sanitize contacts to prevent private number leakage)
$configSrc = Join-Path $ProjectRoot "config"
$configDest = Join-Path $StagingDir "config"
New-Item -ItemType Directory -Path $configDest -Force | Out-Null
Get-ChildItem -Path $configSrc -File | Where-Object {
    $_.Name -ne "contacts.json" -and $_.Name -notmatch '__pycache__'
} | ForEach-Object {
    Copy-Item $_.FullName (Join-Path $configDest $_.Name) -Force
}

# Ensure contacts.json in staging uses the sanitized example template
$contactsExample = Join-Path $configSrc "contacts.json.example"
if (Test-Path $contactsExample) {
    Copy-Item $contactsExample (Join-Path $configDest "contacts.json.example") -Force
}

# Assets placeholder directory
$assetsDest = Join-Path $StagingDir "assets"
New-Item -ItemType Directory -Path $assetsDest -Force | Out-Null

# Installer directory
$installerDest = Join-Path $StagingDir "installer"
New-Item -ItemType Directory -Path $installerDest -Force | Out-Null
Copy-Item (Join-Path $ProjectRoot "installer\setup_environment.ps1") (Join-Path $installerDest "setup_environment.ps1") -Force

# Dashboard directory (copy source and dist, EXCLUDE node_modules)
$dashSrc = Join-Path $ProjectRoot "dashboard"
$dashDest = Join-Path $StagingDir "dashboard"
New-Item -ItemType Directory -Path $dashDest -Force | Out-Null

$dashRootFiles = @("package.json", "package-lock.json", "index.html", "vite.config.ts", "tsconfig.json", "tsconfig.node.json")
foreach ($df in $dashRootFiles) {
    $src = Join-Path $dashSrc $df
    if (Test-Path $src) {
        Copy-Item $src (Join-Path $dashDest $df) -Force
    }
}

$dashSubdirs = @("electron", "src", "dist")
foreach ($sd in $dashSubdirs) {
    $srcSub = Join-Path $dashSrc $sd
    $destSub = Join-Path $dashDest $sd
    if (Test-Path $srcSub) {
        New-Item -ItemType Directory -Path $destSub -Force | Out-Null
        Get-ChildItem -Path $srcSub -Recurse -File | ForEach-Object {
            $rel = $_.FullName.Substring($srcSub.Length).TrimStart('\', '/')
            $targetFile = Join-Path $destSub $rel
            $targetParent = Split-Path -Parent $targetFile
            if (-not (Test-Path $targetParent)) {
                New-Item -ItemType Directory -Path $targetParent -Force | Out-Null
            }
            Copy-Item $_.FullName $targetFile -Force
        }
    }
}

Write-Host "  [OK] Staging file tree assembled." -ForegroundColor Green

# ------------------------------------------------------------------------------
# 2. RIGOROUS SECURITY AND SENSITIVE FILE AUDIT
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "[2/4] Executing sensitive file and secret audit on staging tree..." -ForegroundColor Cyan

$AuditViolations = @()

# Rule A: No active .env files (only .env.example allowed)
$envFiles = Get-ChildItem -Path $StagingDir -Recurse -Force -Filter ".env" -ErrorAction SilentlyContinue
foreach ($f in $envFiles) {
    $AuditViolations += "Illegal sensitive environment file detected: $($f.FullName)"
}

# Rule B: No cookies.txt or personal cookie files
$cookieFiles = Get-ChildItem -Path $StagingDir -Recurse -Force -Filter "*cookie*.txt" -ErrorAction SilentlyContinue
foreach ($f in $cookieFiles) {
    if ($f.Length -gt 0) {
        $fLen = $f.Length
        $AuditViolations += "Illegal cookie file with data detected: $($f.FullName) ($fLen bytes)"
    }
}

# Rule C: No PyWhatKit database or WhatsApp logs
$whatkitDb = Get-ChildItem -Path $StagingDir -Recurse -Force -Filter "PyWhatKit_DB.txt" -ErrorAction SilentlyContinue
foreach ($f in $whatkitDb) {
    $AuditViolations += "Illegal WhatsApp database file detected: $($f.FullName)"
}

# Rule D: No personal chat histories
$chatFiles = Get-ChildItem -Path $StagingDir -Recurse -Force -Filter "chat_*.json" -ErrorAction SilentlyContinue
foreach ($f in $chatFiles) {
    $AuditViolations += "Personal chat history file detected: $($f.FullName)"
}

# Rule E: No pre-existing virtual environments or node_modules
$venvDirs = Get-ChildItem -Path $StagingDir -Recurse -Directory | Where-Object { $_.Name -in @(".venv", "venv", "node_modules") }
foreach ($d in $venvDirs) {
    $AuditViolations += "Machine-specific environment directory detected: $($d.FullName)"
}

# Rule F: No precompiled bytecode or test caches
$cacheDirs = Get-ChildItem -Path $StagingDir -Recurse -Directory | Where-Object { $_.Name -in @("__pycache__", ".pytest_cache", ".vscode") }
foreach ($d in $cacheDirs) {
    $AuditViolations += "Developer cache directory detected: $($d.FullName)"
}

# Rule G: Scan staged text files for real API key patterns or hardcoded developer paths
$TextExtensions = @(".py", ".json", ".example", ".txt", ".bat", ".ps1", ".md")
$stagedTextFiles = Get-ChildItem -Path $StagingDir -Recurse -File | Where-Object { $TextExtensions -contains $_.Extension }

foreach ($tf in $stagedTextFiles) {
    try {
        $content = Get-Content -Path $tf.FullName -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
        if ($content) {
            # Check for live API key pattern line-by-line (must only be placeholder or env getter)
            $lines = Get-Content -Path $tf.FullName -Encoding UTF8 -ErrorAction SilentlyContinue
            foreach ($line in $lines) {
                if ($line -match '^\s*COE_AI_KEY\s*=\s*(?<val>[^\r\n#]+)') {
                    $val = $matches['val'].Trim().Trim('"', "'", '`', '.')
                    $knownPlaceholders = @("PASTE_YOUR_API_KEY_HERE", "your_actual_api_key_here", "your_api_key_here", "")
                    if ($val.StartsWith("os.getenv") -or $val.StartsWith("str(") -or $val.StartsWith("getenv")) {
                        continue
                    }
                    if ($val -and -not ($knownPlaceholders -contains $val)) {
                        $AuditViolations += "Non-placeholder API key detected in '$($tf.FullName)': $line"
                    }
                }
            }
            # Check for developer specific path
            if ($content -match 'C:\\Users\\Sundaram\\AppData') {
                $AuditViolations += "Developer-specific absolute path detected in '$($tf.FullName)'"
            }
        }
    } catch {}
}

if ($AuditViolations.Count -gt 0) {
    Write-Host ""
    Write-Host "========================================================================" -ForegroundColor Red
    Write-Host " [SECURITY AUDIT FAILED] Packaging Aborted!" -ForegroundColor Red
    Write-Host "========================================================================" -ForegroundColor Red
    foreach ($v in $AuditViolations) {
        Write-Host "  - $v" -ForegroundColor Red
    }
    Write-Host "Cleaning staging directory..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $StagingRoot -ErrorAction SilentlyContinue
    exit 1
}

Write-Host "  [OK] Sensitive-file audit passed with ZERO violations." -ForegroundColor Green
Write-Host "  [OK] All staged files verified safe for public distribution." -ForegroundColor Green

# ------------------------------------------------------------------------------
# 3. BUILD ZIP PACKAGE
# ------------------------------------------------------------------------------
if (-not $SkipZipCompression) {
    Write-Host ""
    Write-Host "[3/4] Compressing release package into ZIP archive..." -ForegroundColor Cyan
    Write-Host "  Target: $OutputPath" -ForegroundColor Gray

    if (Test-Path $OutputPath) {
        Remove-Item -Force $OutputPath -ErrorAction SilentlyContinue
    }

    # Compress staging tree
    Compress-Archive -Path "$StagingDir\*" -DestinationPath $OutputPath -Force

    if (-not (Test-Path $OutputPath)) {
        Write-Host "[ERROR] Failed to produce output ZIP at '$OutputPath'!" -ForegroundColor Red
        exit 1
    }

    $zipItem = Get-Item $OutputPath
    $sizeMb = [math]::Round($zipItem.Length / 1MB, 2)
    $zipBytes = $zipItem.Length
    Write-Host "  [OK] ZIP archive generated: $sizeMb MB ($zipBytes bytes)." -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "[3/4] ZIP compression skipped per parameter." -ForegroundColor Gray
}

# ------------------------------------------------------------------------------
# 4. CLEANUP & SUMMARY
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "[4/4] Finalizing package..." -ForegroundColor Cyan

# Clean up staging directory
if (Test-Path $StagingRoot) {
    Remove-Item -Recurse -Force $StagingRoot -ErrorAction SilentlyContinue
    Write-Host "  [OK] Temporary staging directory cleaned." -ForegroundColor Green
}

Write-Host ""
Write-Host "========================================================================" -ForegroundColor Green
Write-Host "          LIGHT AI V1.0 DISTRIBUTION PACKAGE CREATED" -ForegroundColor Green
Write-Host "========================================================================" -ForegroundColor Green
Write-Host "  Archive Location : $OutputPath" -ForegroundColor White
if (Test-Path $OutputPath) {
    $finalZip = Get-Item $OutputPath
    $finalMb = [math]::Round($finalZip.Length / 1MB, 2)
    $finalBytes = $finalZip.Length
    Write-Host "  Archive Size     : $finalMb MB ($finalBytes bytes)" -ForegroundColor White
}
Write-Host "  Security Audit   : PASSED (No keys, personal cookies, or chat logs)" -ForegroundColor White
Write-Host "  Target Platform  : Windows 10/11 (64-bit)" -ForegroundColor White
Write-Host "========================================================================" -ForegroundColor Green
Write-Host ""

exit 0
