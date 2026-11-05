"""
Windows Registry and App Paths helper for Light AI V1.0.
Queries HKLM and HKCU App Paths safely to locate installed executables.
"""

import os
import shutil
from typing import Optional
from utils.logger import logger

try:
    import winreg
except ImportError:
    winreg = None  # Fallback for non-Windows test environments


def get_app_path_from_registry(executable_name: str) -> Optional[str]:
    """
    Looks up the executable in Windows Registry App Paths:
    - HKEY_CURRENT_USER\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths
    - HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths
    """
    if winreg is None:
        return None

    sub_key = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{executable_name}"
    roots = [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]

    for root in roots:
        try:
            with winreg.OpenKey(root, sub_key) as key:
                val, _ = winreg.QueryValueEx(key, "")
                if val:
                    # Registry values might have quotes around them
                    clean_val = val.strip('"\'' )
                    if os.path.exists(clean_val):
                        return clean_val
        except (OSError, FileNotFoundError):
            continue

    return None


def resolve_executable_path(executable_name: str) -> Optional[str]:
    """
    Resolves the full path to an executable:
    1. Check Windows Registry App Paths (HKCU & HKLM).
    2. Check system PATH via shutil.which.
    Returns the resolved path if found and valid, otherwise None.
    """
    if not executable_name:
        return None

    # 1. Check Registry App Paths
    reg_path = get_app_path_from_registry(executable_name)
    if reg_path:
        return reg_path

    # 2. Check system PATH
    which_path = shutil.which(executable_name)
    if which_path and os.path.exists(which_path):
        return which_path

    return None
