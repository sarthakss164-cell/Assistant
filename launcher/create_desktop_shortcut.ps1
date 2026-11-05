<#
================================================================================
LIGHT AI V1.0 — Desktop Shortcut Generator
Creates a Windows Desktop shortcut pointing to Launch_LIGHT_AI.bat.
================================================================================
#>

[CmdletBinding()]
param(
    [string]$ShortcutName = "LIGHT AI V1.0"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$BatchLauncher = Join-Path $ProjectRoot "Launch_LIGHT_AI.bat"

if (-not (Test-Path $BatchLauncher)) {
    Write-Host "[ERROR] Target launcher not found at '$BatchLauncher'!" -ForegroundColor Red
    exit 1
}

$DesktopPath = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop)
$ShortcutFile = Join-Path $DesktopPath "$ShortcutName.lnk"

Write-Host "Creating Desktop shortcut for LIGHT AI V1.0..." -ForegroundColor Cyan
Write-Host " Target : $BatchLauncher" -ForegroundColor Gray
Write-Host " Folder : $ProjectRoot" -ForegroundColor Gray
Write-Host " Dest   : $ShortcutFile" -ForegroundColor Gray

try {
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut($ShortcutFile)
    $Shortcut.TargetPath = $BatchLauncher
    $Shortcut.WorkingDirectory = $ProjectRoot
    $Shortcut.Description = "Launch LIGHT AI V1.0 Tactical HUD & Assistant"
    
    # Check if a project icon (.ico) exists in assets or root; if not, do not invent one
    $PotentialIcons = @(
        (Join-Path $ProjectRoot "assets\app.ico"),
        (Join-Path $ProjectRoot "assets\icon.ico"),
        (Join-Path $ProjectRoot "icon.ico")
    )
    $FoundIcon = $null
    foreach ($ico in $PotentialIcons) {
        if (Test-Path $ico) {
            $FoundIcon = $ico
            break
        }
    }
    if ($FoundIcon) {
        $Shortcut.IconLocation = $FoundIcon
        Write-Host " Icon   : $FoundIcon" -ForegroundColor Green
    } else {
        Write-Host " Icon   : System Default (No custom .ico in project assets)" -ForegroundColor Gray
    }

    $Shortcut.Save()
    Write-Host ""
    Write-Host "[OK] Desktop shortcut created successfully!" -ForegroundColor Green
    Write-Host "You can now double-click '$ShortcutName' on your Desktop to launch LIGHT AI." -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Failed to create shortcut: $_" -ForegroundColor Red
    exit 1
}

exit 0

