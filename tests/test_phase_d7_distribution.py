"""
Tests for Phase D7: Smart ZIP Distribution System for LIGHT AI V1.0.

Verifies:
1. SETUP.bat existence and error-tolerant delegation.
2. requirements.txt and requirements_runtime.txt completeness and parity.
3. dashboard/package.json production script configuration.
4. Portability of config/app_allowlist.json.
5. Template safety (.env.example, contacts.json.example).
6. Packaging script existence and security audit enforcement.
7. Distribution ZIP archive structure, integrity, and sensitive-file exclusions.
8. Zero private data / credentials in packaged artifacts.
"""

import json
import os
import re
import zipfile
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_setup_batch_exists_and_delegates():
    """SETUP.bat must exist, navigate to %~dp0, run setup_environment.ps1, and pause on error."""
    setup_bat = PROJECT_ROOT / "SETUP.bat"
    assert setup_bat.exists(), "SETUP.bat must exist in project root"
    content = setup_bat.read_text(encoding="utf-8", errors="ignore")
    assert "%~dp0" in content
    assert "setup_environment.ps1" in content
    assert "pause" in content.lower()


def test_requirements_files():
    """requirements.txt and requirements_runtime.txt must have essential dependencies."""
    req_file = PROJECT_ROOT / "requirements.txt"
    runtime_file = PROJECT_ROOT / "requirements_runtime.txt"
    
    assert req_file.exists(), "requirements.txt must exist"
    assert runtime_file.exists(), "requirements_runtime.txt must exist"

    req_text = req_file.read_text(encoding="utf-8")
    runtime_text = runtime_file.read_text(encoding="utf-8")

    essential_pkgs = [
        "aiohttp",
        "openai",
        "pyaudio",
        "SpeechRecognition",
        "edge-tts",
        "pygame",
        "psutil",
        "yt-dlp",
        "python-vlc",
        "pywhatkit",
    ]

    for pkg in essential_pkgs:
        assert re.search(rf"\b{re.escape(pkg)}\b", req_text, re.IGNORECASE), f"{pkg} missing from requirements.txt"
        assert re.search(rf"\b{re.escape(pkg)}\b", runtime_text, re.IGNORECASE), f"{pkg} missing from requirements_runtime.txt"

    # Runtime requirements should not require test frameworks like pytest
    assert "pytest" not in runtime_text.lower(), "pytest should not be in requirements_runtime.txt"


def test_dashboard_package_json_prod_script():
    """dashboard/package.json must contain electron:prod script for zero-dev-server production."""
    pkg_json_path = PROJECT_ROOT / "dashboard" / "package.json"
    assert pkg_json_path.exists(), "dashboard/package.json must exist"
    
    with open(pkg_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    scripts = data.get("scripts", {})
    assert "electron:prod" in scripts, "electron:prod script must exist in package.json"
    assert "electron ." in scripts["electron:prod"]


def test_app_allowlist_portability():
    """config/app_allowlist.json must not hardcode developer user directories."""
    allowlist_path = PROJECT_ROOT / "config" / "app_allowlist.json"
    assert allowlist_path.exists()
    
    with open(allowlist_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for app_name, app_data in data.items():
        exec_path = app_data.get("executable_path", "")
        assert not exec_path.startswith("C:\\Users\\"), (
            f"App {app_name} has hardcoded developer user path: {exec_path}"
        )


def test_env_and_contacts_templates():
    """.env.example and contacts.json.example must be sanitized and safe for public release."""
    env_example = PROJECT_ROOT / ".env.example"
    assert env_example.exists()
    env_content = env_example.read_text(encoding="utf-8")
    assert "COE_AI_KEY=PASTE_YOUR_API_KEY_HERE" in env_content
    assert "COE_AI_BASE_URL=" in env_content

    contacts_example = PROJECT_ROOT / "config" / "contacts.json.example"
    assert contacts_example.exists()
    with open(contacts_example, "r", encoding="utf-8") as f:
        contacts_data = json.load(f)
    
    # Ensure all contacts in example have dummy phone numbers
    for name, number in contacts_data.items():
        assert number.startswith("+9198765") or number.startswith("+12345") or number.startswith("+9100000"), (
            f"Contact {name} has non-dummy number: {number}"
        )


def test_launcher_scripts_exist():
    """Ensure launcher and setup orchestrator scripts are present."""
    assert (PROJECT_ROOT / "launcher" / "start_light_ai.ps1").exists()
    assert (PROJECT_ROOT / "launcher" / "create_desktop_shortcut.ps1").exists()
    assert (PROJECT_ROOT / "installer" / "setup_environment.ps1").exists()
    assert (PROJECT_ROOT / "installer" / "package_release.ps1").exists()
    assert (PROJECT_ROOT / "README_INSTALLATION.md").exists()


def test_start_light_ai_resolution_hierarchy():
    r"""start_light_ai.ps1 must prioritize .venv\Scripts\python.exe and support electron:prod."""
    script_path = PROJECT_ROOT / "launcher" / "start_light_ai.ps1"
    content = script_path.read_text(encoding="utf-8")
    assert ".venv\\Scripts\\python.exe" in content
    assert "dist\\index.html" in content
    assert "electron:prod" in content


def test_distribution_zip_contents():
    """Verify that dist/LIGHT_AI_V1.0_Windows.zip exists and contains essential files."""
    zip_path = PROJECT_ROOT / "dist" / "LIGHT_AI_V1.0_Windows.zip"
    assert zip_path.exists(), f"Distribution zip not found at {zip_path}"

    with zipfile.ZipFile(zip_path, "r") as z:
        names = set(z.namelist())

        # Essential root files
        expected_root = [
            "SETUP.bat",
            "Launch_LIGHT_AI.bat",
            "README_INSTALLATION.md",
            ".env.example",
            "requirements.txt",
            "requirements_runtime.txt",
            "main.py",
        ]
        for ef in expected_root:
            assert ef in names, f"Expected {ef} in zip root"

        # Essential subsystems
        assert any(n.startswith("actions/") or n.startswith("actions\\") for n in names)
        assert any(n.startswith("core/") or n.startswith("core\\") for n in names)
        assert any(n.startswith("speech/") or n.startswith("speech\\") for n in names)
        assert any(n.startswith("memory/") or n.startswith("memory\\") for n in names)
        assert any(n.startswith("config/") or n.startswith("config\\") for n in names)
        assert any(n.startswith("installer/") or n.startswith("installer\\") for n in names)
        assert any(n.startswith("launcher/") or n.startswith("launcher\\") for n in names)
        assert any(n.startswith("dashboard/") or n.startswith("dashboard\\") for n in names)

        # Precompiled production dashboard build
        prod_index = any(n in ("dashboard/dist/index.html", "dashboard\\dist\\index.html") for n in names)
        assert prod_index, "dashboard/dist/index.html must be present in zip for zero-dev-server launch"


def test_distribution_zip_strict_exclusions():
    """Verify that no sensitive files, dev caches, or local virtual environments leaked into the zip."""
    zip_path = PROJECT_ROOT / "dist" / "LIGHT_AI_V1.0_Windows.zip"
    assert zip_path.exists()

    forbidden_patterns = [
        "__pycache__",
        ".pyc",
        "node_modules",
        ".pytest_cache",
        ".vscode",
        ".git",
        "cookies.txt",
        "pywhatkit_db.txt",
    ]

    with zipfile.ZipFile(zip_path, "r") as z:
        for entry in z.namelist():
            entry_lower = entry.lower()
            
            # Check forbidden substrings
            for pattern in forbidden_patterns:
                assert pattern not in entry_lower, f"Forbidden entry '{entry}' found in ZIP (matches {pattern})"

            # Check for live .env file (only .env.example allowed)
            assert not entry_lower.endswith("/.env") and not entry_lower.endswith("\\.env") and entry_lower != ".env", (
                f"Active .env file found in ZIP: {entry}"
            )

            # Check for personal chat history files
            assert not re.search(r"chat_.*\.json$", entry_lower), (
                f"Personal chat history file found in ZIP: {entry}"
            )

            # Check for active contacts.json (only contacts.json.example allowed)
            assert not entry_lower.endswith("contacts.json"), (
                f"Real contacts.json found in ZIP: {entry}"
            )


def test_distribution_zip_content_safety():
    """Inspect text contents inside zip to ensure no leaked keys or developer appdata paths."""
    zip_path = PROJECT_ROOT / "dist" / "LIGHT_AI_V1.0_Windows.zip"
    assert zip_path.exists()

    scannable_exts = (".py", ".json", ".example", ".txt", ".bat", ".ps1", ".md")

    with zipfile.ZipFile(zip_path, "r") as z:
        for entry in z.infolist():
            if any(entry.filename.endswith(ext) for ext in scannable_exts):
                with z.open(entry.filename) as f:
                    try:
                        text = f.read().decode("utf-8")
                    except UnicodeDecodeError:
                        continue

                    # Developer appdata path check
                    assert "C:\\Users\\Sundaram\\AppData" not in text, (
                        f"Developer-specific AppData path leaked in {entry.filename}"
                    )

                    # Secret API key check
                    for line in text.splitlines():
                        if "COE_AI_KEY=" in line:
                            val = line.split("COE_AI_KEY=")[-1].strip().strip('"\'`.')
                            assert val in (
                                "PASTE_YOUR_API_KEY_HERE",
                                "your_actual_api_key_here",
                                "",
                            ), f"Real API key detected in {entry.filename}: {line}"
