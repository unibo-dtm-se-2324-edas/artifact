"""
Configuration module for the EDAS application.

Loads sensitive keys (like ENTSOE_API_KEY) and static settings 
(like timezones) from environment variables (.env file).
"""

import os
from typing import Final

from dotenv import load_dotenv

# Load environment variables from a .env file (if present)
# This allows for easy configuration in development without setting system variables.
load_dotenv()

# -----------------------------
# ENTSO-E API configuration
# -----------------------------

# Fetch the raw API key string from the environment variables
_raw_key = os.getenv("ENTSOE_API_KEY")

# Define the API key as a typed Constant (Final) for use in other modules.
# Fallback to an empty string if the environment variable is not set.
ENTSOE_API_KEY: Final[str] = _raw_key or ""

# Define the default timezone for ENTSO-E data (which uses CET/Brussels time)
TZ_EUROPE: Final[str] = "Europe/Brussels"


def debug_enabled() -> bool:
    """
    Reads EDAS_DEBUG from the environment. Defaults to False (safe) when
    unset. Accepts "1", "true", "yes" (case-insensitive) as truthy.
    """
    return os.environ.get("EDAS_DEBUG", "").strip().lower() in ("1", "true", "yes")