"""
Unit and integration tests for LIGHT AI V1.0 One-Click Desktop Launcher.
Tests pre-flight verification, duplicate instance prevention, path resolution,
process tracking safety, and desktop shortcut generation.
"""

import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LAUNCHER_BAT = PROJECT_ROOT / "Launch_LIGHT_AI.bat"
START_PS1 = PROJECT_ROOT / "launcher" / "start_light_ai.ps1"
SHORTCUT_PS1 = PROJECT_ROOT / "launcher" / "create_desktop_shortcut.ps1"


def test_launcher_files_exist():
    """Verify that all launcher files exist in their specified locations."""
    assert LAUNCHER_BAT.exists(), f"Launch_LIGHT_AI.bat missing at {LAUNCHER_BAT}"
    assert START_PS1.exists(), f"start_light_ai.ps1 missing at {START_PS1}"
    assert SHORTCUT_PS1.exists(), f"create_desktop_shortcut.ps1 missing at {SHORTCUT_PS1}"


def test_batch_launcher_syntax_and_safety():
    """Verify batch file content resolves %~dp0, checks script existence, and runs PowerShell safely."""
    content = LAUNCHER_BAT.read_text(encoding="utf-8")
    assert "%~dp0" in content
    assert "start_light_ai.ps1" in content
    assert "ExecutionPolicy Bypass" in content
    assert "-NoProfile" in content
    assert "exit /b" in content


def test_powershell_script_structure():
    """Verify start_light_ai.ps1 has pre-flight checks, duplicate port detection, and PID-specific cleanup."""
    content = START_PS1.read_text(encoding="utf-8")
    assert "Test-PortListening" in content or "8765" in content
    assert "main.py" in content
    assert "package.json" in content
    assert "node_modules" in content
    assert "taskkill" in content
    # Ensure broad taskkill is NOT used
    assert "taskkill /IM python.exe" not in content
    assert "taskkill.exe /IM python.exe" not in content
    assert "taskkill /IM node.exe" not in content


def test_desktop_shortcut_script_no_fake_icons():
    """Verify shortcut script does not invent fake icon paths and sets working directory."""
    content = SHORTCUT_PS1.read_text(encoding="utf-8")
    assert "CreateShortcut" in content
    assert "Launch_LIGHT_AI.bat" in content
    assert "WorkingDirectory" in content
    assert "Test-Path" in content  # Checks existence before setting icon


def test_preflight_failure_on_invalid_python_path():
    """Verify launcher fails with non-zero exit code and clear diagnostic message when Python path is invalid."""
    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(START_PS1),
        "-PythonPath",
        "C:\\NonExistentPath\\python_fake_light_ai.exe",
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(PROJECT_ROOT))
    assert res.returncode != 0
    assert "not found" in res.stdout.lower() or "not found" in res.stderr.lower()
    assert "NonExistentPath" in res.stdout or "NonExistentPath" in res.stderr


def test_duplicate_instance_prevention():
    """Verify launcher refuses to start if port 8765 is already bound by another process."""
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        # Retry briefly if previous test left socket in OS TIME_WAIT
        bound = False
        for _ in range(20):
            try:
                server_sock.bind(("127.0.0.1", 8765))
                bound = True
                break
            except (OSError, PermissionError):
                time.sleep(0.5)

        assert bound, "Could not bind port 8765 for duplicate instance test (port busy)"
        server_sock.listen(1)

        # Attempt to run launcher in backend-only mode
        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(START_PS1),
            "-BackendOnly",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(PROJECT_ROOT), timeout=15)
        assert res.returncode != 0
        assert "8765" in res.stdout
        assert "already running" in res.stdout.lower() or "in use" in res.stdout.lower()
    finally:
        server_sock.close()


def test_desktop_shortcut_creation():
    """Verify create_desktop_shortcut.ps1 executes successfully and produces a .lnk file."""
    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(SHORTCUT_PS1),
        "-ShortcutName",
        "LIGHT AI Test Shortcut",
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(PROJECT_ROOT), timeout=15)
    assert res.returncode == 0
    assert "[OK]" in res.stdout

    # Check OneDrive Desktop first if present, then standard Desktop
    onedrive = os.environ.get("OneDrive")
    desktop_candidates = []
    if onedrive:
        desktop_candidates.append(Path(onedrive) / "Desktop" / "LIGHT AI Test Shortcut.lnk")
    desktop_candidates.append(Path(os.environ.get("USERPROFILE", "")) / "Desktop" / "LIGHT AI Test Shortcut.lnk")
    
    found_shortcut = None
    for candidate in desktop_candidates:
        if candidate.exists():
            found_shortcut = candidate
            break

    try:
        assert found_shortcut is not None and found_shortcut.exists()
    finally:
        for candidate in desktop_candidates:
            if candidate.exists():
                candidate.unlink()
