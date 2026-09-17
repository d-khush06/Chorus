"""
config.py
=========
Chorus Verification MCP — Configuration and API-key bootstrap.

All external credentials are loaded from environment variables.
This module is imported at server startup; any missing required key
causes an immediate SystemExit (fail-loud, fail-early — never on the
first tool call).

Rate-limit constants are defined here as named constants (never magic
numbers inline) so they can be tuned without hunting through tool code.
"""

import os
import sys
from typing import Optional

# ---------------------------------------------------------------------------
# Reverse-image-search provider
# ---------------------------------------------------------------------------
# Provider tag controls which reverse-image-search backend is used.
# Supported values: "google_lens"
# (Add new providers to tools/reverse_search.py and update this comment.)
REVERSE_SEARCH_PROVIDER: str = os.getenv("REVERSE_SEARCH_PROVIDER", "google_lens")

# ---------------------------------------------------------------------------
# Search API provider
# ---------------------------------------------------------------------------
# Provider tag controls which web-search backend is used.
# Supported values: "serper"
WEB_SEARCH_PROVIDER: str = os.getenv("WEB_SEARCH_PROVIDER", "serper")

# ---------------------------------------------------------------------------
# Rate-limit constants  (requests / window)
#
# Sized to each API's documented free-tier limits.
# All tools use a simple fixed-window counter.  Each constant is the
# max number of requests allowed within RATE_WINDOW_SECONDS.
# ---------------------------------------------------------------------------

RATE_WINDOW_SECONDS: int = 60          # common 1-minute window for all tools

# Google Lens / reverse image: custom Search JSON API — 100 req/day free.
# We conservatively allow 10 per minute to stay well within daily budget.
REVERSE_SEARCH_RATE_LIMIT: int = 10

# YouTube Data API v3 — 10 000 units/day; a videos.list costs 1 unit.
# 60 req/min is a comfortable per-minute cap.
UPLOAD_HISTORY_RATE_LIMIT: int = 60

# Google Fact Check Tools API — 10 000 req/day free.
# 60 req/min is a comfortable per-minute cap.
FACT_CHECK_RATE_LIMIT: int = 60

# Serper / web-search — free tier is 2 500 req/month; cap 10/min.
WEB_SEARCH_RATE_LIMIT: int = 10

# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------

# Maximum number of retry attempts on transient failures (timeout, 429, 5xx).
MAX_RETRIES: int = 2

# Base delay in seconds for exponential back-off.  Actual delay for attempt N
# (0-indexed) is BASE_BACKOFF_SECONDS * 2^N.
BASE_BACKOFF_SECONDS: float = 1.0

# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------
# Resolved relative to this file's directory so it works from any cwd.
_HERE: str = os.path.dirname(os.path.abspath(__file__))
AUDIT_LOG_DIR: str = os.path.join(_HERE, "audit_logs", "verification_mcp")

# ---------------------------------------------------------------------------
# Required environment variables
# Each entry: (env_var_name, description_for_error_message)
# ---------------------------------------------------------------------------
_REQUIRED_KEYS: list[tuple[str, str]] = [
    ("YOUTUBE_API_KEY",    "YouTube Data API v3 — console.cloud.google.com"),
    ("FACTCHECK_API_KEY",  "Google Fact Check Tools API — console.cloud.google.com"),
    ("SERPER_API_KEY",     "Serper web-search — serper.dev"),
    ("GOOGLE_CSE_API_KEY", "Google Custom Search API key — console.cloud.google.com"),
    ("GOOGLE_CSE_CX",      "Google Custom Search Engine ID — programmablesearchengine.google.com"),
]

# ---------------------------------------------------------------------------
# Public accessors — these are the symbols the tool modules import.
# ---------------------------------------------------------------------------

YOUTUBE_API_KEY:    str = ""
FACTCHECK_API_KEY:  str = ""
SERPER_API_KEY:     str = ""
GOOGLE_CSE_API_KEY: str = ""
GOOGLE_CSE_CX:      str = ""


def load_and_validate() -> dict[str, bool]:
    """
    Load all API keys from the environment and validate required ones.

    Called once at server startup.  Returns a dict mapping each key name
    to True (found) or False (missing) for the startup summary banner.

    Raises SystemExit if any required key is absent so the server never
    starts in a misconfigured state.
    """
    global YOUTUBE_API_KEY, FACTCHECK_API_KEY, SERPER_API_KEY
    global GOOGLE_CSE_API_KEY, GOOGLE_CSE_CX

    YOUTUBE_API_KEY    = os.getenv("YOUTUBE_API_KEY", "")
    FACTCHECK_API_KEY  = os.getenv("FACTCHECK_API_KEY", "")
    SERPER_API_KEY     = os.getenv("SERPER_API_KEY", "")
    GOOGLE_CSE_API_KEY = os.getenv("GOOGLE_CSE_API_KEY", "")
    GOOGLE_CSE_CX      = os.getenv("GOOGLE_CSE_CX", "")

    key_status: dict[str, bool] = {}
    missing: list[str] = []

    for var_name, description in _REQUIRED_KEYS:
        value = os.getenv(var_name, "")
        found = bool(value.strip())
        key_status[var_name] = found
        if not found:
            missing.append(f"  • {var_name}  ({description})")

    if missing:
        missing_block = "\n".join(missing)
        sys.exit(
            f"\n[chorus_verification_mcp] FATAL — missing required API key(s):\n"
            f"{missing_block}\n\n"
            f"Set the above environment variables (or add them to a .env file)\n"
            f"before starting the server.  See .env.example for details.\n"
        )

    return key_status


def get_key(name: str) -> Optional[str]:
    """Return a loaded key value by env-var name, or None if not set."""
    return os.getenv(name) or None
