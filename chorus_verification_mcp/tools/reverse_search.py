"""
tools/reverse_search.py
=======================
Chorus Verification MCP — Tool: reverse_search_frame

Calls an external reverse-image-search API to find where a frame (or any
image) has appeared online.  The provider is controlled by the
REVERSE_SEARCH_PROVIDER constant in config.py; currently "google_lens"
uses Google's Custom Search API with image-by-URL.

Rate limit:  REVERSE_SEARCH_RATE_LIMIT requests per RATE_WINDOW_SECONDS.
Retries:     up to MAX_RETRIES times on timeout / 429 / 5xx.
On 4xx (not 429): immediate structured error, no retry.
"""

import time
import base64
import logging
import os
import tempfile

import httpx

import config
import audit

log = logging.getLogger("chorus.verification_mcp.reverse_search")

# ---------------------------------------------------------------------------
# Fixed-window rate limiter state (module-level, process-local)
# ---------------------------------------------------------------------------
_window_start: float = time.monotonic()
_window_count: int = 0

TOOL_NAME = "reverse_search_frame"


# ---------------------------------------------------------------------------
# Input schema (validated before any external call)
# ---------------------------------------------------------------------------

def _validate_input(args: dict) -> tuple[bool, str]:
    """
    Return (True, "") on valid input, or (False, reason) on invalid.

    Required fields:
        image    : str  — base64-encoded image bytes OR a local file path
        case_id  : str  — non-empty string
    """
    if not isinstance(args.get("case_id"), str) or not args["case_id"].strip():
        return False, "'case_id' must be a non-empty string"
    if not isinstance(args.get("image"), str) or not args["image"].strip():
        return False, "'image' must be a non-empty string (base64 data or file path)"
    return True, ""


# ---------------------------------------------------------------------------
# Rate-limit helper
# ---------------------------------------------------------------------------

def _check_rate_limit() -> tuple[bool, int]:
    """
    Return (allowed, retry_after_seconds).
    Updates the fixed-window counter.
    """
    global _window_start, _window_count
    now = time.monotonic()
    if now - _window_start >= config.RATE_WINDOW_SECONDS:
        _window_start = now
        _window_count = 0

    if _window_count >= config.REVERSE_SEARCH_RATE_LIMIT:
        retry_after = int(config.RATE_WINDOW_SECONDS - (now - _window_start)) + 1
        return False, retry_after

    _window_count += 1
    return True, 0


# ---------------------------------------------------------------------------
# Image resolution helper
# ---------------------------------------------------------------------------

def _resolve_image_url(image_str: str) -> tuple[str | None, str | None]:
    """
    Given the 'image' field (base64 or file path), return a publicly-
    accessible URL suitable for the Google Custom Search imageUrl param.

    For a local file / base64 payload this is a limitation: the Google
    Custom Search API requires a public URL.  We detect this and return
    an error message so the caller can surface it cleanly.

    Returns: (url_or_none, error_or_none)
    """
    s = image_str.strip()

    # Already an http(s) URL — use as-is.
    if s.startswith("http://") or s.startswith("https://"):
        return s, None

    # Local file path that exists on disk — we cannot serve it publicly;
    # return a clear structured error.
    if os.path.exists(s):
        return None, (
            "Local file paths cannot be sent to the Google reverse-image API "
            "directly. Convert the frame to a publicly accessible URL first, "
            "or pass a base64-encoded string."
        )

    # Assume base64-encoded bytes.  We cannot upload them to a public host
    # from within this tool, so return a helpful error.
    try:
        base64.b64decode(s, validate=True)
        return None, (
            "Base64-encoded images cannot be sent to the Google reverse-image "
            "API without a public URL. Upload the image to a temporary host "
            "first and pass the resulting URL as 'image'."
        )
    except Exception:
        pass

    return None, f"'image' value is not a valid URL, file path, or base64 string."


# ---------------------------------------------------------------------------
# Core API call
# ---------------------------------------------------------------------------

def _call_google_cse_image_search(image_url: str) -> dict:
    """
    Call the Google Custom Search JSON API in image-search mode.

    Returns the parsed response dict on success, or raises httpx.HTTPError
    for the retry layer to handle.
    """
    params = {
        "key":        config.GOOGLE_CSE_API_KEY,
        "cx":         config.GOOGLE_CSE_CX,
        "searchType": "image",
        "q":          image_url,
        "num":        10,
    }
    resp = httpx.get(
        "https://www.googleapis.com/customsearch/v1",
        params=params,
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()


def _parse_cse_response(data: dict) -> list[dict]:
    """Extract matches from a Google CSE response."""
    items = data.get("items", [])
    matches = []
    for item in items:
        matches.append({
            "source_url":        item.get("link", ""),
            "first_seen_date":   item.get("snippet", "")[:20],  # best available
            "similarity_score":  None,  # CSE does not return a score
        })
    return matches


# ---------------------------------------------------------------------------
# Public tool entry point
# ---------------------------------------------------------------------------

def run(args: dict) -> dict:
    """
    Execute the reverse_search_frame tool.

    Input schema:
        image    : str  — public HTTPS URL (preferred), local file path, or base64
        case_id  : str

    Output schema:
        {matches: [{source_url, first_seen_date, similarity_score}],
         match_count: int, case_id: str}
      or on error:
        {error: true, reason: str, case_id: str}
    """
    case_id = args.get("case_id", "unknown")

    # --- input validation ---
    valid, reason = _validate_input(args)
    if not valid:
        result = {"error": True, "reason": reason, "case_id": case_id}
        return result

    # Sanitised inputs for audit (never log raw keys — keys are in config, not args)
    safe_inputs = {"image": args["image"][:80] + ("..." if len(args["image"]) > 80 else ""),
                   "case_id": case_id}
    audit.log_tool_start(TOOL_NAME, case_id, safe_inputs)

    # --- rate limit ---
    allowed, retry_after = _check_rate_limit()
    if not allowed:
        result = {
            "error": True,
            "reason": "rate_limited",
            "retry_after_seconds": retry_after,
            "case_id": case_id,
        }
        audit.log_tool_result(TOOL_NAME, case_id, result)
        return result

    # --- resolve image to URL ---
    image_url, resolve_err = _resolve_image_url(args["image"])
    if resolve_err:
        result = {"error": True, "reason": resolve_err, "case_id": case_id}
        audit.log_tool_result(TOOL_NAME, case_id, result)
        return result

    # --- call with retries ---
    last_error: str = ""
    for attempt in range(config.MAX_RETRIES + 1):
        try:
            if config.REVERSE_SEARCH_PROVIDER == "google_lens":
                data = _call_google_cse_image_search(image_url)
            else:
                result = {
                    "error": True,
                    "reason": f"Unknown REVERSE_SEARCH_PROVIDER: {config.REVERSE_SEARCH_PROVIDER!r}",
                    "case_id": case_id,
                }
                audit.log_tool_result(TOOL_NAME, case_id, result)
                return result

            matches = _parse_cse_response(data)
            result = {
                "matches":     matches,
                "match_count": len(matches),
                "case_id":     case_id,
            }
            audit.log_tool_result(TOOL_NAME, case_id, result)
            return result

        except httpx.TimeoutException as exc:
            last_error = f"Timeout: {exc}"
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 429:
                last_error = f"HTTP 429 Too Many Requests"
            elif 400 <= status < 500:
                # 4xx client error — do not retry
                result = {
                    "error":  True,
                    "reason": f"Client error HTTP {status}: {exc.response.text[:200]}",
                    "case_id": case_id,
                }
                audit.log_tool_result(TOOL_NAME, case_id, result)
                return result
            else:
                last_error = f"HTTP {status}: {exc.response.text[:200]}"
        except Exception as exc:
            last_error = str(exc)

        if attempt < config.MAX_RETRIES:
            backoff = config.BASE_BACKOFF_SECONDS * (2 ** attempt)
            log.warning("reverse_search attempt %d failed (%s); retrying in %.1fs",
                        attempt + 1, last_error, backoff)
            time.sleep(backoff)

    result = {"error": True, "reason": f"All retries exhausted: {last_error}", "case_id": case_id}
    audit.log_tool_result(TOOL_NAME, case_id, result)
    return result
