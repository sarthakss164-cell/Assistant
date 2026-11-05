"""
Web search action for Light AI V1.0.
Performs Google Search and YouTube Search in Brave Browser using proper URL encoding and instance reuse.
"""

from typing import Tuple
from actions.browser import open_google_search, open_youtube


def search_google(query: str) -> Tuple[bool, str]:
    """
    Constructs a properly URL-encoded Google search URL and opens it in Brave.
    """
    return open_google_search(query)


def search_youtube(query: str) -> Tuple[bool, str]:
    """
    Constructs a properly URL-encoded YouTube search URL (or homepage if empty) and opens it in Brave.
    """
    return open_youtube(query)
