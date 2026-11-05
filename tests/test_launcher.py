"""
Unit tests for AppLauncher, Registry Resolution, and Browser Routing.
Verifies separate browser routing (Chrome, Brave, Edge), window focusing,
allowlist enforcement, and rejection of arbitrary commands.
"""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from actions.app_launcher import AppLauncher
from actions.browser import (
    open_or_focus_browser,
    open_url_in_browser,
    is_browser_running,
    find_browser_window,
    focus_browser_window,
    BROWSER_DEFAULT_PATHS,
)


@pytest.fixture
def launcher():
    return AppLauncher()


def test_allowlist_matches_approved_apps(launcher):
    """Verifies that all approved apps and their aliases are correctly matched."""
    assert launcher.find_allowed_app("brave") is not None
    assert launcher.find_allowed_app("brave browser") is not None
    assert launcher.find_allowed_app("chrome") is not None
    assert launcher.find_allowed_app("google chrome") is not None
    assert launcher.find_allowed_app("edge") is not None
    assert launcher.find_allowed_app("microsoft edge") is not None
    assert launcher.find_allowed_app("browser") is not None

    assert launcher.find_allowed_app("notepad") is not None
    assert launcher.find_allowed_app("notes") is not None

    assert launcher.find_allowed_app("vscode") is not None
    assert launcher.find_allowed_app("vs code") is not None
    assert launcher.find_allowed_app("code") is not None

    assert launcher.find_allowed_app("whatsapp") is not None
    assert launcher.find_allowed_app("whatsapp web") is not None


def test_reject_unallowlisted_applications(launcher):
    """Verifies that unapproved apps or commands are strictly rejected."""
    forbidden = [
        "calculator",
        "calc",
        "powershell",
        "cmd",
        "cmd.exe",
        "taskmgr",
        "explorer",
        "malicious.exe",
        "notepad & calc",
        "spotify",
    ]
    for target in forbidden:
        matched = launcher.find_allowed_app(target)
        assert matched is None
        success, msg = launcher.launch(target)
        assert success is False
        assert "approved applications mein nahi hai" in msg


@patch("actions.app_launcher.open_or_focus_browser")
def test_separate_browser_routing_chrome_brave_edge(mock_browser_open, launcher):
    """
    Verifies that 'open Chrome', 'open Brave', and 'open Edge' each route
    to their respective browser handler without cross-redirection.
    """
    # 1. Chrome
    launcher.launch("chrome")
    mock_browser_open.assert_called_with("chrome")

    launcher.launch("google chrome")
    mock_browser_open.assert_called_with("chrome")

    # 2. Brave
    launcher.launch("brave")
    mock_browser_open.assert_called_with("brave")

    launcher.launch("brave browser")
    mock_browser_open.assert_called_with("brave")

    # 3. Edge
    launcher.launch("edge")
    mock_browser_open.assert_called_with("edge")

    launcher.launch("microsoft edge")
    mock_browser_open.assert_called_with("edge")

    # 4. Generic browser -> routes to preferred browser (brave)
    launcher.launch("browser")
    mock_browser_open.assert_called_with("brave")


@patch("subprocess.Popen")
@patch("actions.browser.focus_browser_window", return_value=True)
@patch("actions.browser.find_browser_window", return_value=12345)
@patch("actions.browser.is_browser_running", return_value=True)
@patch("actions.browser.get_browser_path", return_value=r"C:\Program Files\Google\Chrome\Application\chrome.exe")
@patch("os.path.isfile", return_value=True)
def test_open_or_focus_browser_running_with_window(
    mock_isfile, mock_path, mock_running, mock_find, mock_focus, mock_popen
):
    """Verifies that an already running browser with a usable window is focused, not launched anew."""
    success, msg = open_or_focus_browser("chrome")
    assert success is True
    assert "window ko samne le aayi hoon" in msg
    mock_focus.assert_called_once_with(12345)
    mock_popen.assert_not_called()


@patch("subprocess.Popen")
@patch("actions.browser.find_browser_window", return_value=None)
@patch("actions.browser.is_browser_running", return_value=True)
@patch("actions.browser.get_browser_path", return_value=r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe")
@patch("os.path.isfile", return_value=True)
def test_open_or_focus_browser_running_no_window(
    mock_isfile, mock_path, mock_running, mock_find, mock_popen
):
    """Verifies that when browser process exists without a usable window, it is safely launched."""
    success, msg = open_or_focus_browser("brave")
    assert success is True
    assert "open kar rahi hoon" in msg
    mock_popen.assert_called_once_with([r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"])


@patch("subprocess.Popen")
@patch("actions.browser.is_browser_running", return_value=False)
@patch("actions.browser.get_browser_path", return_value=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
@patch("os.path.isfile", return_value=True)
def test_open_or_focus_browser_not_running(
    mock_isfile, mock_path, mock_running, mock_popen
):
    """Verifies that when browser is not running, it is launched directly."""
    success, msg = open_or_focus_browser("edge")
    assert success is True
    assert "open kar rahi hoon" in msg
    mock_popen.assert_called_once_with([r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"])


@patch("actions.browser.get_browser_path", return_value=None)
def test_open_or_focus_browser_missing_executable(mock_path):
    """Verifies that missing browser executable is reported clearly without crashing."""
    success, msg = open_or_focus_browser("edge")
    assert success is False
    assert "system par nahi mila" in msg


@patch("subprocess.Popen")
@patch("actions.browser.focus_browser_window", return_value=True)
@patch("actions.browser.find_browser_window", return_value=9999)
@patch("actions.browser.is_browser_running", return_value=True)
@patch("actions.browser.get_browser_path", return_value=r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe")
@patch("os.path.isfile", return_value=True)
def test_open_url_reuses_window_and_focuses(
    mock_isfile, mock_path, mock_running, mock_find, mock_focus, mock_popen
):
    """Verifies that opening a URL in a running browser passes the URL and brings window forward."""
    url = "https://www.youtube.com"
    success, msg = open_url_in_browser(url, "brave")
    assert success is True
    assert "existing window mein khol diya gaya hai" in msg
    mock_popen.assert_called_once_with([r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe", url])
    mock_focus.assert_called_once_with(9999)


@patch("actions.app_launcher.resolve_executable_path")
@patch("os.startfile")
def test_successful_app_launch_notepad(mock_startfile, mock_resolve, launcher):
    """Verifies successful launch of an allowlisted app (Notepad) when executable is found."""
    mock_resolve.return_value = r"C:\Windows\System32\notepad.exe"
    
    success, msg = launcher.launch("notepad")
    assert success is True
    assert "Notepad open kar rahi hoon" in msg or "Notepad khol diya gaya hai" in msg
    mock_startfile.assert_called_once()
    assert mock_startfile.call_args[0][0].lower() == r"c:\windows\system32\notepad.exe"


@patch("actions.app_launcher.resolve_executable_path")
def test_app_not_found_on_system(mock_resolve, launcher):
    """Verifies graceful handling when an allowlisted app executable is missing."""
    mock_resolve.return_value = None

    launcher.allowlist["test_missing"] = {
        "display_name": "Missing App",
        "executable": "missing.exe",
        "executable_path": "",
        "aliases": ["missing"]
    }
    success, msg = launcher.launch("missing")
    assert success is False
    assert "system par nahi mila" in msg


@patch("os.path.isfile", return_value=True)
@patch("os.startfile")
def test_user_configured_executable_path_success(mock_startfile, mock_isfile, launcher):
    """Verifies that an explicitly configured valid executable_path is launched directly."""
    custom_path = r"C:\CustomApps\MyEditor.exe"
    launcher.allowlist["custom_editor"] = {
        "display_name": "Custom Editor",
        "executable": "editor.exe",
        "executable_path": custom_path,
        "aliases": ["custom editor", "my editor"]
    }

    success, msg = launcher.launch("my editor")
    assert success is True
    assert "Custom Editor open kar rahi hoon" in msg or "Custom Editor khol diya gaya hai" in msg
    mock_startfile.assert_called_once_with(custom_path)


@patch("subprocess.Popen")
@patch("os.path.isfile", return_value=True)
def test_user_configured_launch_arguments(mock_isfile, mock_popen, launcher):
    """Verifies that launch_arguments are passed safely via subprocess without shell."""
    custom_path = r"C:\CustomApps\MyTool.exe"
    launcher.allowlist["custom_tool"] = {
        "display_name": "Custom Tool",
        "executable": "tool.exe",
        "executable_path": custom_path,
        "launch_arguments": ["--debug", "--verbose"],
        "aliases": ["my tool"]
    }

    success, msg = launcher.launch("my tool")
    assert success is True
    mock_popen.assert_called_once_with([custom_path, "--debug", "--verbose"])
