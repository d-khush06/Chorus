"""
tools/fact_check.py
===================
Chorus Verification MCP — Tool: fact_check_claim

Calls the Google Fact Check Tools API (ClaimSearch endpoint) to find
existing fact-checks that match the supplied claim text.

The API is free up to FACT_CHECK_RATE_LIMIT requests per minute.

Rate limit:  FACT_CHECK_RATE_LIMIT requests per RATE_WINDOW_SECONDS.
Retries:     up to MAX_RETRIES times on timeout / 429 / 5xx.
"""

import time
import logging

import httpx

import config
import audit

log = logging.getLogger("chorus.verification_mcp.fact_check")

TOOL_NAME = "fact_check_claim"

# Verdict normalisation map: ClaimReview ratingValue -> our canonical verdict
_VERDICT_MAP: dict[str, str] = {
    "true":        "true",
    "mostly true": "true",
    "false":       "false",
    "mostly false":"false",
    "misleading":  "misleading",
    "half true":   "misleading",
    "mixture":     "misleading",
    "pants on fire": "false",
}

# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------
_window_start: float = time.monotonic()
_window_count: int = 0


def _check_rate_limit() -> tuple[bool, int]:
    global _window_start, _window_count
    now = time.monotonic()
    if now - _window_start >= config.RATE_WINDOW_SECONDS:
        _window_start = now
        _window_count = 0
    if _window_count >= config.FACT_CHECK_RATE_LIMIT:
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
    if not isinstance(args.get("claim_text"), str) or not args["claim_text"].strip():
        return False, "'claim_text' must be a non-empty string"
    if len(args["claim_text"]) > 1000:
        return False, "'claim_text' must be ≤ 1000 characters"
    return True, ""


# ---------------------------------------------------------------------------
# API call
# ---------------------------------------------------------------------------

def _call_factcheck_api(claim_text: str) -> dict:
    """
    Call the Google Fact Check Tools API ClaimSearch endpoint.
    Returns the parsed JSON response dict.
    """
    params = {
        "key":         config.FACTCHECK_API_KEY,
        "query":       claim_text,
        "languageCode": "en",
        "pageSize":    5,
    }
    resp = httpx.get(
        "https://factchecktools.googleapis.com/v1alpha1/claims:search",
        params=params,
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()


def _normalise_verdict(rating_value: str) -> str:
    """Map a raw ClaimReview ratingValue to our canonical verdict."""
    key = (rating_value or "").strip().lower()
    return _VERDICT_MAP.get(key, "unverified")


def _parse_response(data: dict) -> tuple[str, list[dict]]:
    """
    Extract verdict and matched fact-checks from a ClaimSearch response.

    Returns: (verdict, matched_factchecks)
    """
    claims = data.get("claims", [])
    if not claims:
        return "unverified", []

    matched: list[dict] = []
    verdicts: list[str] = []

    for claim in claims:
        for review in claim.get("claimReview", []):
            rating = review.get("textualRating", "")
            verdict = _normalise_verdict(rating)
            verdicts.append(verdict)
            matched.append({
                "source":  review.get("publisher", {}).get("name", ""),
                "url":     review.get("url", ""),
                "rating":  rating,
            })

    # Aggregate verdict: if any review says false → false; misleading → misleading;
    # all true → true; otherwise unverified.
    if "false" in verdicts:
        final_verdict = "false"
    elif "misleading" in verdicts:
        final_verdict = "misleading"
    elif all(v == "true" for v in verdicts) and verdicts:
        final_verdict = "true"
    else:
        final_verdict = "unverified"

    return final_verdict, matched


# ---------------------------------------------------------------------------
# Public tool entry point
# ---------------------------------------------------------------------------

def run(args: dict) -> dict:
    """
    Execute the fact_check_claim tool.

    Input schema:
        claim_text : str  — text of the claim to fact-check (≤ 1000 chars)
        case_id    : str

    Output schema:
        {verdict: "true"|"false"|"misleading"|"unverified",
         matched_factchecks: [{source, url, rating}],
         case_id: str}
      or:
        {error: true, reason: str, case_id: str}
    """
    case_id = args.get("case_id", "unknown")

    valid, reason = _validate_input(args)
    if not valid:
        return {"error": True, "reason": reason, "case_id": case_id}

    safe_inputs = {
        "claim_text": args["claim_text"][:120] + ("..." if len(args["claim_text"]) > 120 else ""),
        "case_id": case_id,
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
            data = _call_factcheck_api(args["claim_text"])
            verdict, matched = _parse_response(data)
            result = {
                "verdict":            verdict,
                "matched_factchecks": matched,
                "case_id":            case_id,
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
            log.warning("fact_check attempt %d failed (%s); retrying in %.1fs",
                        attempt + 1, last_error, backoff)
            time.sleep(backoff)

    result = {
        "error":   True,
        "reason":  f"All retries exhausted: {last_error}",
        "case_id": case_id,
    }
    audit.log_tool_result(TOOL_NAME, case_id, result)
    return result
