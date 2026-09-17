"""
tools/upload_history.py
=======================
Chorus Verification MCP — Tool: check_upload_history

Queries the YouTube Data API v3 to verify when a video was first published,
who published it, and whether it has been re-uploaded from other sources.

Rate limit:  UPLOAD_HISTORY_RATE_LIMIT requests per RATE_WINDOW_SECONDS.
Retries:     up to MAX_RETRIES times on timeout / 429 / 5xx.
"""

import time
import re
import logging
from datetime import datetime

import httpx

import config
import audit

log = logging.getLogger("chorus.verification_mcp.upload_history")

TOOL_NAME = "check_upload_history"

# YouTube video-ID extraction pattern (handles full URLs and bare IDs)
_YT_ID_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|shorts/|embed/)|youtu\.be/)([A-Za-z0-9_-]{11})"
)

# ---------------------------------------------------------------------------
# Rate limiter (fixed-window, module-level)
# ---------------------------------------------------------------------------
_window_start: float = time.monotonic()
_window_count: int = 0


def _check_rate_limit() -> tuple[bool, int]:
    global _window_start, _window_count
    now = time.monotonic()
    if now - _window_start >= config.RATE_WINDOW_SECONDS:
        _window_start = now
        _window_count = 0
    if _window_count >= config.UPLOAD_HISTORY_RATE_LIMIT:
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
    if not isinstance(args.get("video_url_or_id"), str) or not args["video_url_or_id"].strip():
        return False, "'video_url_or_id' must be a non-empty string"
    return True, ""


# ---------------------------------------------------------------------------
# YouTube ID extraction
# ---------------------------------------------------------------------------

def _extract_video_id(video_url_or_id: str) -> str | None:
    """
    Return an 11-character YouTube video ID from a URL or bare ID.
    Returns None if extraction fails.
    """
    s = video_url_or_id.strip()
    # Bare 11-character video ID
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", s):
        return s
    m = _YT_ID_RE.search(s)
    if m:
        return m.group(1)
    return None


# ---------------------------------------------------------------------------
# YouTube Data API v3 call
# ---------------------------------------------------------------------------

def _fetch_video_metadata(video_id: str) -> dict:
    """
    Call videos.list with snippet and statistics parts.
    Returns the parsed response dict.  Raises httpx.HTTPError on failure.
    """
    params = {
        "key":  config.YOUTUBE_API_KEY,
        "id":   video_id,
        "part": "snippet,statistics",
    }
    resp = httpx.get(
        "https://www.googleapis.com/youtube/v3/videos",
        params=params,
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()


def _fetch_channel_metadata(channel_id: str) -> dict:
    """Call channels.list to get channel creation date."""
    params = {
        "key":  config.YOUTUBE_API_KEY,
        "id":   channel_id,
        "part": "snippet",
    }
    resp = httpx.get(
        "https://www.googleapis.com/youtube/v3/channels",
        params=params,
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()


def _search_reuploads(title: str) -> list[str]:
    """
    Search YouTube for the same title to detect potential re-uploads.
    Returns a list of video URLs found (excluding original not applicable here).
    """
    params = {
        "key":        config.YOUTUBE_API_KEY,
        "q":          title,
        "part":       "snippet",
        "type":       "video",
        "maxResults": 5,
    }
    resp = httpx.get(
        "https://www.googleapis.com/youtube/v3/search",
        params=params,
        timeout=15.0,
    )
    resp.raise_for_status()
    data = resp.json()
    urls = []
    for item in data.get("items", []):
        vid_id = item.get("id", {}).get("videoId")
        if vid_id:
            urls.append(f"https://www.youtube.com/watch?v={vid_id}")
    return urls


# ---------------------------------------------------------------------------
# Public tool entry point
# ---------------------------------------------------------------------------

def run(args: dict) -> dict:
    """
    Execute the check_upload_history tool.

    Input schema:
        video_url_or_id : str  — YouTube URL or bare video ID
        case_id         : str

    Output schema:
        {actual_upload_date: str|null, channel_name: str,
         channel_created_date: str|null,
         prior_reuploads_found: bool, reupload_sources: [str, ...],
         case_id: str}
      or:
        {error: true, reason: str, case_id: str}
    """
    case_id = args.get("case_id", "unknown")

    valid, reason = _validate_input(args)
    if not valid:
        return {"error": True, "reason": reason, "case_id": case_id}

    safe_inputs = {"video_url_or_id": args["video_url_or_id"], "case_id": case_id}
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

    video_id = _extract_video_id(args["video_url_or_id"])
    if not video_id:
        result = {
            "error": True,
            "reason": (
                f"Could not extract a YouTube video ID from: "
                f"{args['video_url_or_id']!r}"
            ),
            "case_id": case_id,
        }
        audit.log_tool_result(TOOL_NAME, case_id, result)
        return result

    last_error = ""
    for attempt in range(config.MAX_RETRIES + 1):
        try:
            # Fetch video metadata
            video_data = _fetch_video_metadata(video_id)
            items = video_data.get("items", [])
            if not items:
                result = {
                    "error":  True,
                    "reason": f"No YouTube video found for ID: {video_id}",
                    "case_id": case_id,
                }
                audit.log_tool_result(TOOL_NAME, case_id, result)
                return result

            snippet = items[0].get("snippet", {})
            upload_date     = snippet.get("publishedAt")   # ISO 8601
            channel_name    = snippet.get("channelTitle", "")
            channel_id      = snippet.get("channelId", "")
            video_title     = snippet.get("title", "")

            # Fetch channel creation date
            channel_created_date = None
            if channel_id:
                try:
                    ch_data = _fetch_channel_metadata(channel_id)
                    ch_items = ch_data.get("items", [])
                    if ch_items:
                        channel_created_date = (
                            ch_items[0].get("snippet", {}).get("publishedAt")
                        )
                except Exception as e:
                    log.warning("Could not fetch channel metadata: %s", e)

            # Search for re-uploads
            reupload_sources: list[str] = []
            prior_reuploads_found = False
            if video_title:
                try:
                    urls = _search_reuploads(video_title)
                    # Exclude the original video itself
                    reupload_sources = [
                        u for u in urls
                        if video_id not in u
                    ]
                    prior_reuploads_found = len(reupload_sources) > 0
                except Exception as e:
                    log.warning("Re-upload search failed: %s", e)

            result = {
                "actual_upload_date":    upload_date,
                "channel_name":          channel_name,
                "channel_created_date":  channel_created_date,
                "prior_reuploads_found": prior_reuploads_found,
                "reupload_sources":      reupload_sources,
                "case_id":               case_id,
            }
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
            log.warning("upload_history attempt %d failed (%s); retrying in %.1fs",
                        attempt + 1, last_error, backoff)
            time.sleep(backoff)

    result = {
        "error":   True,
        "reason":  f"All retries exhausted: {last_error}",
        "case_id": case_id,
    }
    audit.log_tool_result(TOOL_NAME, case_id, result)
    return result
