"""
Browser management and automation helper for Light AI V1.0.
Supports independent routing and window detection/focusing for Brave, Chrome, and Edge.
Reuses existing windows and tabs, and uses configurable preferred browser for web tasks.
All spoken responses use natural, feminine Hindi/Hinglish grammar.
"""

import json
import os
import subprocess
import urllib.parse
from pathlib import Path
from typing import Optional, Tuple, Dict, Set
import ctypes
from ctypes import wintypes
import psutil

from config.settings import ALLOWLIST_FILE, PREFERRED_BROWSER
from utils.logger import logger
from utils.registry_helper import resolve_executable_path

# Standard Windows Default Installation Paths
BROWSER_DEFAULT_PATHS = {
    "brave": r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
}

BROWSER_PROCESS_NAMES = {
    "brave": "brave.exe",
    "chrome": "chrome.exe",
    "edge": "msedge.exe",
}

BROWSER_DISPLAY_NAMES = {
    "brave": "Brave",
    "chrome": "Google Chrome",
    "edge": "Microsoft Edge",
}

# Windows User32 and Kernel32 functions for window management
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def get_browser_path(browser_key: str, allowlist_path: Path = ALLOWLIST_FILE) -> Optional[str]:
    """
    Resolves the browser executable path:
    1. Check config/app_allowlist.json for explicit 'executable_path'.
    2. Check standard default installation location.
    3. Check Windows Registry App Paths.
    """
    key = browser_key.strip().lower()

    # 1. Allowlist configuration
    if allowlist_path.exists():
        try:
            with open(allowlist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                entry = data.get(key, {})
                configured_path = entry.get("executable_path")
                if configured_path and os.path.isfile(configured_path):
                    return configured_path
        except Exception as e:
            logger.debug(f"Could not load allowlist for {key} path: {e}")

    # 2. Standard default path
    default_path = BROWSER_DEFAULT_PATHS.get(key)
    if default_path and os.path.isfile(default_path):
        return default_path

    # Secondary check for Edge 64-bit if x86 wasn't found
    if key == "edge":
        edge_64 = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
        if os.path.isfile(edge_64):
            return edge_64

    # 3. Windows Registry App Paths
    proc_name = BROWSER_PROCESS_NAMES.get(key, f"{key}.exe")
    reg_path = resolve_executable_path(proc_name)
    if reg_path and os.path.isfile(reg_path):
        return reg_path

    return None


def is_browser_running(browser_key: str) -> bool:
    """
    Checks currently running Windows processes to detect if the specified browser is running.
    """
    key = browser_key.strip().lower()
    target_proc = BROWSER_PROCESS_NAMES.get(key, f"{key}.exe").lower()

    try:
        for p in psutil.process_iter(["name"]):
            try:
                name = p.info.get("name")
                if name and name.lower() == target_proc:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as e:
        logger.debug(f"Error checking {key} process status: {e}")
    return False


def get_browser_pids(browser_key: str) -> Set[int]:
    """Retrieves all active PIDs for the given browser."""
    key = browser_key.strip().lower()
    target_proc = BROWSER_PROCESS_NAMES.get(key, f"{key}.exe").lower()
    pids = set()

    try:
        for p in psutil.process_iter(["name", "pid"]):
            try:
                name = p.info.get("name")
                if name and name.lower() == target_proc:
                    pids.add(p.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as e:
        logger.debug(f"Error retrieving PIDs for {key}: {e}")
    return pids


def find_browser_window(browser_key: str) -> Optional[int]:
    """
    Finds a visible, usable top-level window HWND for the specified browser.
    Inspects both current desktop and Default interactive desktop.
    """
    pids = get_browser_pids(browser_key)
    if not pids:
        return None

    found_hwnds = []

    def check_hwnd(hwnd):
        if not user32.IsWindowVisible(hwnd):
            return

        # Skip cloaked windows (virtual desktops / suspended UWP)
        cloaked = wintypes.DWORD()
        try:
            ctypes.windll.dwmapi.DwmGetWindowAttribute(
                hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked)
            )
            if cloaked.value != 0:
                return
        except Exception:
            pass

        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return

        lp_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(lp_pid))
        if lp_pid.value in pids:
            found_hwnds.append(hwnd)

    def enum_cb(hwnd, lparam):
        check_hwnd(hwnd)
        return True

    try:
        # 1. Try EnumWindows on current desktop
        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

        # 2. If not found, try EnumDesktopWindows on 'Default' interactive desktop
        if not found_hwnds:
            hdesk = user32.OpenDesktopW("Default", 0, False, 0x0100)  # DESKTOP_ENUMERATE
            if not hdesk:
                hdesk = user32.OpenInputDesktop(0, False, 0x0100)
            if hdesk:
                user32.EnumDesktopWindows.argtypes = [wintypes.HANDLE, WNDENUMPROC, wintypes.LPARAM]
                user32.EnumDesktopWindows.restype = wintypes.BOOL
                user32.EnumDesktopWindows(hdesk, WNDENUMPROC(enum_cb), 0)
                user32.CloseDesktop(hdesk)
    except Exception as e:
        logger.debug(f"Error enumerating windows for {browser_key}: {e}")

    return found_hwnds[0] if found_hwnds else None


def focus_browser_window(hwnd: int) -> bool:
    """
    Restores and brings a window to the foreground.
    """
    if not hwnd:
        return False

    try:
        # SW_RESTORE = 9 (restores minimized window)
        user32.ShowWindow(hwnd, 9)
        cur_thread = kernel32.GetCurrentThreadId()
        fg_hwnd = user32.GetForegroundWindow()
        fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0

        if cur_thread != fg_thread and fg_thread != 0:
            user32.AttachThreadInput(cur_thread, fg_thread, True)
            user32.BringWindowToTop(hwnd)
            res = user32.SetForegroundWindow(hwnd)
            user32.AttachThreadInput(cur_thread, fg_thread, False)
        else:
            user32.BringWindowToTop(hwnd)
            res = user32.SetForegroundWindow(hwnd)

        return bool(res)
    except Exception as e:
        logger.error(f"Failed to focus window HWND {hwnd}: {e}")
        return False


def open_or_focus_browser(browser_key: str) -> Tuple[bool, str]:
    """
    Opens the requested browser or brings its existing window to the foreground.
    Never creates a duplicate window if an existing usable window can be focused.
    Returns:
        (success: bool, female_hindi_message: str)
    """
    key = browser_key.strip().lower()
    display_name = BROWSER_DISPLAY_NAMES.get(key, key.capitalize())
    path = get_browser_path(key)

    if not path or not os.path.isfile(path):
        logger.error(f"Browser executable not found for: {key}")
        return False, f"Maaf kijiye, {display_name} system par nahi mila."

    # Check if already running
    if is_browser_running(key):
        hwnd = find_browser_window(key)
        if hwnd:
            logger.info(f"{display_name} is running with HWND {hwnd}. Bringing window to foreground.")
            focus_browser_window(hwnd)
            return True, f"{display_name} window ko samne le aayi hoon."
        else:
            logger.info(f"{display_name} process is running but has no usable window. Launching...")
            try:
                subprocess.Popen([path])
                return True, f"{display_name} open kar rahi hoon."
            except Exception as e:
                logger.error(f"Failed to launch {display_name}: {e}")
                return False, f"{display_name} open karne mein error aayi: {e}"

    # Browser not running: launch it
    try:
        logger.info(f"Launching {display_name} at '{path}'")
        subprocess.Popen([path])
        return True, f"{display_name} open kar rahi hoon."
    except Exception as e:
        logger.error(f"Failed to launch {display_name}: {e}")
        return False, f"{display_name} open karne mein error aayi: {e}"


def open_url_in_browser(url: str, browser_key: Optional[str] = None) -> Tuple[bool, str]:
    """
    Opens a URL in the specified browser (or configured PREFERRED_BROWSER).
    Reuses existing browser instance via Chromium/Edge IPC and brings window forward.
    """
    target_key = (browser_key or PREFERRED_BROWSER).strip().lower()
    display_name = BROWSER_DISPLAY_NAMES.get(target_key, target_key.capitalize())
    path = get_browser_path(target_key)

    if not path or not os.path.isfile(path):
        logger.error(f"Executable not found for browser '{target_key}' at: {path}")
        return False, f"Maaf kijiye, {display_name} system par nahi mila."

    already_running = is_browser_running(target_key)
    try:
        logger.info(f"Opening URL in {display_name} (already_running={already_running}): {url}")
        subprocess.Popen([path, url])

        if already_running:
            # Focus the window so user sees the newly opened tab
            hwnd = find_browser_window(target_key)
            if hwnd:
                focus_browser_window(hwnd)
            return True, f"{display_name} ke existing window mein khol diya gaya hai."
        else:
            return True, f"{display_name} open kar rahi hoon."
    except Exception as e:
        logger.error(f"Failed to open URL in {display_name}: {e}")
        return False, f"Browser open karne mein dikkat aayi: {e}"


def open_google_search(query: str, browser_key: Optional[str] = None) -> Tuple[bool, str]:
    """
    Constructs a properly URL-encoded Google search query and opens it in preferred browser.
    """
    clean_query = query.strip()
    if not clean_query:
        return False, "Kripya Google par search karne ke liye query batayein."

    encoded = urllib.parse.quote_plus(clean_query)
    url = f"https://www.google.com/search?q={encoded}"
    success, _ = open_url_in_browser(url, browser_key)
    if success:
        return True, f"Google par '{clean_query}' search kar rahi hoon."
    return False, "Browser open karne mein dikkat aayi."


def open_youtube(query: str = "", browser_key: Optional[str] = None) -> Tuple[bool, str]:
    """
    Opens YouTube homepage (if query is empty) or search results in preferred browser.
    """
    clean_query = query.strip()
    if not clean_query:
        url = "https://www.youtube.com"
        success, _ = open_url_in_browser(url, browser_key)
        if success:
            return True, "YouTube open kar rahi hoon."
        return False, "YouTube open karne mein dikkat aayi."

    encoded = urllib.parse.quote_plus(clean_query)
    url = f"https://www.youtube.com/results?search_query={encoded}"
    success, _ = open_url_in_browser(url, browser_key)
    if success:
        return True, f"YouTube par '{clean_query}' search kar rahi hoon."
    return False, "YouTube search karne mein dikkat aayi."


def open_whatsapp_web(browser_key: Optional[str] = None) -> Tuple[bool, str]:
    """
    Opens WhatsApp Web in preferred browser reusing any existing instance.
    """
    url = "https://web.whatsapp.com"
    success, _ = open_url_in_browser(url, browser_key)
    if success:
        return True, "WhatsApp Web open kar rahi hoon."
    return False, "WhatsApp Web open karne mein dikkat aayi."


# Backward compatibility helpers
def is_brave_running() -> bool:
    return is_browser_running("brave")


def get_brave_path(allowlist_path: Path = ALLOWLIST_FILE) -> str:
    path = get_browser_path("brave", allowlist_path)
    return path or BROWSER_DEFAULT_PATHS["brave"]


def open_in_brave(url: Optional[str] = None, brave_path: Optional[str] = None) -> Tuple[bool, str]:
    if url:
        return open_url_in_browser(url, "brave")
    return open_or_focus_browser("brave")


def open_whatsapp_web_in_brave() -> Tuple[bool, str]:
    return open_whatsapp_web("brave")
