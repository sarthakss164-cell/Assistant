"""
Identity action for Light AI V1.0.
Provides the exact approved fixed identity response without any LLM.
"""

from typing import Tuple
from config.settings import FIXED_IDENTITY_RESPONSE


def get_identity_response() -> Tuple[bool, str]:
    """
    Returns the fixed deterministic identity response.
    Approved response: 'Main Light AI hoon, jise mere Boss ne banaya hai.'
    """
    return (True, FIXED_IDENTITY_RESPONSE)
