"""
Configuration module for the EDAS application.

Loads sensitive keys (like ENTSOE_API_KEY) and static settings 
(like timezones) from environment variables (.env file).
"""

import os
from typing import Final

from dotenv import load_dotenv

load_dotenv()

_raw_key = os.getenv("ENTSOE_API_KEY")

ENTSOE_API_KEY: Final[str] = _raw_key or ""

TZ_EUROPE: Final[str] = "Europe/Brussels"


def debug_enabled() -> bool:
    """
    Reads EDAS_DEBUG from the environment. Defaults to False (safe) when
    unset. Accepts "1", "true", "yes" (case-insensitive) as truthy.
    """
    return os.environ.get("EDAS_DEBUG", "").strip().lower() in ("1", "true", "yes")