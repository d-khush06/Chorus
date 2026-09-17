"""
tools/web_search_fetch.py
=========================
Chorus Verification MCP — Tool: web_search_fetch

Dual-mode tool:
  • mode="search"  — run a web search via the configured provider (default: Serper)
                     and return a list of {title, url, snippet} results.
  • mode="fetch"   — directly fetch a URL via HTTP and return the extracted
                     plain-text content (HTML stripped via a simple parser).

Rate limit:  WEB_SEARCH_RATE_LIMIT requests per RATE_WINDOW_SECONDS
             (shared across both modes — they share the same quota bucket).
Retries:     up to MAX_RETRIES times on timeout / 429 / 5xx.
"""

import time
import logging
import re
from html.parser import HTMLParser

import httpx

import config
import audit

log = logging.getLogger("chorus.verification_mcp.web_search_fetch")

TOOL_NAME = "web_search_fetch"

# ---------------------------------------------------------------------------
# Rate limiter (shared across both modes)
# ---------------------------------------------------------------------------
_window_start: float = time.monotonic()
_window_count: int = 0


def _check_rate_limit() -> tuple[bool, int]:
    global _window_start, _window_count
    now = time.monotonic()
    if now - _window_start >= config.RATE_WINDOW_SECONDS:
        _window_start = now
        _window_count = 0
    if _window_count >= config.WEB_SEARCH_RATE_LIMIT:
        retry_after = int(config.RATE_WINDOW_SECONDS - (now - _window_start)) + 1
        return False, retry_after
    _window_count += 1
    return True, 0


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def _validate_input(args: dict) -> tuple[bool, str]:
    if not isinstance(args.get("case_id"), str) or not args["case_id"].strip():
        return False, "'case_id' must be a non-empty string"

    mode = args.get("mode")
    if mode not in ("search", "fetch"):
        return False, "'mode' must be 'search' or 'fetch'"

    if mode == "search":
        if not isinstance(args.get("query"), str) or not args["query"].strip():
            return False, "'query' must be a non-empty string when mode='search'"
    else:  # fetch
        url = args.get("url", "")
        if not isinstance(url, str) or not url.strip():
            return False, "'url' is required and must be non-empty when mode='fetch'"
        if not (url.startswith("http://") or url.startswith("https://")):
            return False, "'url' must begin with http:// or https://"

    return True, ""


# ---------------------------------------------------------------------------
# HTML → plain-text extractor
# ---------------------------------------------------------------------------

class _TextExtractor(HTMLParser):
    """Minimal HTMLParser subclass that collects visible text."""

    _SKIP_TAGS = {"script", "style", "noscript", "head", "meta", "link"}

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth: int = 0

    def handle_starttag(self, tag: str, attrs):
        if tag.lower() in self._SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str):
        if tag.lower() in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str):
        if self._skip_depth == 0:
            stripped = data.strip()
            if stripped:
                self._parts.append(stripped)

    def get_text(self) -> str:
        raw = " ".join(self._parts)
        # Collapse whitespace
        return re.sub(r"\s{2,}", " ", raw).strip()


def _extract_text(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html)
        return parser.get_text()[:8000]  # cap at 8 000 chars
    except Exception:
        return html[:2000]  # last-resort raw truncation


# ---------------------------------------------------------------------------
# Search mode — Serper API
# ---------------------------------------------------------------------------

def _call_serper(query: str) -> list[dict]:
    """
    Call the Serper.dev Google Search API.
    Returns a list of {title, url, snippet} dicts.
    """
    headers = {
        "X-API-KEY":    config.SERPER_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {"q": query, "num": 10}
    resp = httpx.post(
        "https://google.serper.dev/search",
        json=payload,
        headers=headers,
        timeout=15.0,
    )
    resp.raise_for_status()
    data = resp.json()

    results: list[dict] = []
    for item in data.get("organic", []):
        results.append({
            "title":   item.get("title", ""),
            "url":     item.get("link", ""),
            "snippet": item.get("snippet", ""),
        })
    return results


# ---------------------------------------------------------------------------
# Fetch mode
# ---------------------------------------------------------------------------

def _fetch_url(url: str) -> tuple[str, str]:
    """
    Fetch a URL and return (plain_text_content, final_url).
    final_url reflects any redirects.
    """
    resp = httpx.get(
        url,
        follow_redirects=True,
        timeout=20.0,
        headers={"User-Agent": "ChorusVerificationMCP/1.0"},
    )
    resp.raise_for_status()
    content_type = resp.headers.get("content-type", "")
    if "html" in content_type:
        text = _extract_text(resp.text)
    else:
        text = resp.text[:8000]
    return text, str(resp.url)


# ---------------------------------------------------------------------------
# Public tool entry point
# ---------------------------------------------------------------------------

def run(args: dict) -> dict:
    """
    Execute the web_search_fetch tool.

    Input schema:
        query   : str  — search query (required for mode='search')
        case_id : str
        mode    : "search" | "fetch"
        url     : str  — required when mode='fetch'

    Output schema (search mode):
        {results: [{title, url, snippet}], case_id: str}
    Output schema (fetch mode):
        {content: str, url: str, case_id: str}
    Error:
        {error: true, reason: str, case_id: str}
    """
    case_id = args.get("case_id", "unknown")

    valid, reason = _validate_input(args)
    if not valid:
        return {"error": True, "reason": reason, "case_id": case_id}

    mode = args["mode"]
    safe_inputs = {
        "mode":    mode,
        "case_id": case_id,
        "query":   args.get("query", "")[:120],
        "url":     args.get("url", ""),
    }
    audit.log_tool_start(TOOL_NAME, case_id, safe_inputs)

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

    last_error = ""
    for attempt in range(config.MAX_RETRIES + 1):
        try:
            if mode == "search":
                if config.WEB_SEARCH_PROVIDER == "serper":
                    results = _call_serper(args["query"])
                else:
                    result = {
                        "error":  True,
                        "reason": f"Unknown WEB_SEARCH_PROVIDER: {config.WEB_SEARCH_PROVIDER!r}",
                        "case_id": case_id,
                    }
                    audit.log_tool_result(TOOL_NAME, case_id, result)
                    return result

                result = {"results": results, "case_id": case_id}
                audit.log_tool_result(TOOL_NAME, case_id, result)
                return result

            else:  # fetch
                text, final_url = _fetch_url(args["url"])
                result = {"content": text, "url": final_url, "case_id": case_id}
                audit.log_tool_result(TOOL_NAME, case_id, result)
                return result

        except httpx.TimeoutException as exc:
            last_error = f"Timeout: {exc}"
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 429:
                last_error = "HTTP 429 Too Many Requests"
            elif 400 <= status < 500:
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
            log.warning("web_search_fetch attempt %d failed (%s); retrying in %.1fs",
                        attempt + 1, last_error, backoff)
            time.sleep(backoff)

    result = {
        "error":   True,
        "reason":  f"All retries exhausted: {last_error}",
        "case_id": case_id,
    }
    audit.log_tool_result(TOOL_NAME, case_id, result)
    return result
