"""
Application launcher action for Light AI V1.0.
Strictly enforces the approved application allowlist (Brave, Chrome, Edge, Notepad, WhatsApp Web, VS Code).
Supports independent browser routing for Brave, Chrome, and Edge without cross-redirecting.
Reuses and focuses existing browser windows where available.
Never executes arbitrary commands or raw shell strings.
"""

import json
import os
import subprocess
import sys
from typing import Dict, Any, Optional, Tuple
from pathlib import Path

from config.settings import ALLOWLIST_FILE, PREFERRED_BROWSER
from utils.logger import logger
from utils.registry_helper import resolve_executable_path
from actions.browser import open_or_focus_browser, open_whatsapp_web


class AppLauncher:
    def __init__(self, allowlist_path: Path = ALLOWLIST_FILE):
        self.allowlist_path = allowlist_path
        self.allowlist = self._load_allowlist()

    def _load_allowlist(self) -> Dict[str, Any]:
        """Loads and parses the app allowlist JSON file."""
        if not self.allowlist_path.exists():
            logger.error(f"Allowlist file not found at: {self.allowlist_path}")
            return {}
        try:
            with open(self.allowlist_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load allowlist JSON: {e}")
            return {}

    def find_allowed_app(self, query: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Matches user query against allowlist keys and aliases.
        Returns (app_key, app_data) if matched, otherwise None.
        """
        clean_query = query.strip().lower()
        if not clean_query:
            return None

        # Generic browser aliases match the preferred browser
        if clean_query in ["browser", "internet"]:
            pref = PREFERRED_BROWSER.lower()
            if pref in self.allowlist:
                return pref, self.allowlist[pref]

        for app_key, app_data in self.allowlist.items():
            if clean_query == app_key:
                return app_key, app_data
            aliases = [a.lower() for a in app_data.get("aliases", [])]
            if clean_query in aliases:
                return app_key, app_data

        return None

    def get_launch_acknowledgement(self, query: str) -> str:
        """
        Determines the deterministic spoken acknowledgement for launching an app
        prior to or concurrent with execution.
        """
        clean_query = query.strip().lower()
        if clean_query in ["chrome", "google chrome"]:
            return "Google Chrome open kar rahi hoon."
        if clean_query in ["brave", "brave browser"]:
            return "Brave open kar rahi hoon."
        if clean_query in ["edge", "microsoft edge", "ms edge"]:
            return "Microsoft Edge open kar rahi hoon."
        if clean_query in ["browser", "internet"]:
            return f"{PREFERRED_BROWSER.capitalize()} open kar rahi hoon."
        if clean_query in ["whatsapp", "whatsapp web"]:
            return "WhatsApp Web open kar rahi hoon."
        if clean_query in ["vs code", "vscode", "code"]:
            return "VS Code open kar rahi hoon."

        matched = self.find_allowed_app(clean_query)
        if matched:
            app_key, app_data = matched
            display_name = app_data.get("display_name", app_key.capitalize())
            return f"{display_name} open kar rahi hoon."

        return f"{query.capitalize()} open kar rahi hoon."

    def launch(self, query: str) -> Tuple[bool, str]:
        """
        Safely attempts to launch or focus an allowlisted application.
        Directs explicit browser queries independently to Chrome, Brave, or Edge.
        Directs generic browser queries to the configured preferred browser.
        Directs WhatsApp queries to WhatsApp Web in preferred browser.
        Returns:
            (success: bool, user_message: str)
        """
        clean_query = query.strip().lower()

        # 1. Independent Browser Routing
        if clean_query in ["chrome", "google chrome"]:
            return open_or_focus_browser("chrome")

        if clean_query in ["brave", "brave browser"]:
            return open_or_focus_browser("brave")

        if clean_query in ["edge", "microsoft edge", "ms edge"]:
            return open_or_focus_browser("edge")

        if clean_query in ["browser", "internet"]:
            return open_or_focus_browser(PREFERRED_BROWSER)

        # 2. WhatsApp Web in Preferred Browser
        if clean_query in ["whatsapp", "whatsapp web"]:
            return open_whatsapp_web()

        # 3. Match against remaining allowlisted applications (e.g. Notepad, VS Code)
        matched = self.find_allowed_app(clean_query)
        if not matched:
            logger.warning(f"Rejected unapproved app launch attempt: '{query}'")
            return (
                False,
                f"Maaf kijiye, '{query}' mere approved applications mein nahi hai."
            )

        app_key, app_data = matched
        display_name = app_data.get("display_name", app_key.capitalize())
        executable_path = app_data.get("executable_path") or app_data.get("path")
        executable = app_data.get("executable")
        protocol = app_data.get("protocol")
        launch_args = app_data.get("launch_arguments") or app_data.get("arguments") or []

        # Handle Protocol-based launching if explicitly specified
        if protocol and hasattr(os, "startfile"):
            try:
                logger.info(f"Launching protocol target: {protocol}")
                os.startfile(protocol)
                return (True, f"{display_name} open kar rahi hoon.")
            except Exception as e:
                logger.warning(f"Protocol launch failed for {protocol}: {e}. Falling back to executable path.")

        # Check explicit user-configured executable_path
        resolved_path = None
        if executable_path:
            clean_path = str(executable_path).strip().strip('"\'' )
            if os.path.isfile(clean_path):
                resolved_path = clean_path
                logger.info(f"Using verified user-configured executable_path for '{display_name}': {resolved_path}")
            else:
                logger.warning(
                    f"Configured executable_path for '{display_name}' does not exist on disk: {clean_path}. "
                    f"Falling back to Registry/PATH discovery."
                )

        # Fallback: Resolve path via Windows Registry App Paths or PATH
        if not resolved_path and executable:
            resolved_path = resolve_executable_path(executable)

        if not resolved_path:
            logger.error(f"Executable for '{display_name}' could not be resolved on this system.")
            return (
                False,
                f"Maaf kijiye, {display_name} aapke system par nahi mila."
            )

        # Safe execution without arbitrary shell
        try:
            logger.info(f"Launching allowlisted application: {display_name} at '{resolved_path}'")
            if launch_args:
                cmd = [resolved_path] + [str(a) for a in launch_args]
                subprocess.Popen(cmd)
            elif hasattr(os, "startfile"):
                os.startfile(resolved_path)
            else:
                subprocess.Popen([resolved_path])
            return (True, f"{display_name} open kar rahi hoon.")
        except Exception as e:
            logger.error(f"Failed to launch application '{display_name}': {e}")
            return (
                False,
                f"Maaf kijiye, {display_name} launch karne mein error aayi."
            )
