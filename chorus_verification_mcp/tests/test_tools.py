"""
tests/test_tools.py
===================
Chorus Verification MCP — Standalone tool tests.

Rules
-----
• All four tools are called directly (not through the MCP Orchestrator).
• No real external API calls — the HTTP layer is mocked using unittest.mock.
• Each tool has at least one happy-path test and one failure-mode test.
• Assertions check the declared output schema shape, not exact values.
• Tests are deterministic and run fully offline.

Run with:
    cd chorus_verification_mcp
    python -m pytest tests/test_tools.py -v
"""

import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock

# ── Path bootstrap ───────────────────────────────────────────────────────────
# Add the package root to sys.path so sibling modules resolve correctly when
# the test is run from inside or outside the chorus_verification_mcp/ dir.
_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG  = os.path.dirname(_HERE)
for _p in (_PKG, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── Inject stub environment variables BEFORE importing config ────────────────
os.environ.setdefault("YOUTUBE_API_KEY",    "test-yt-key")
os.environ.setdefault("FACTCHECK_API_KEY",  "test-fc-key")
os.environ.setdefault("SERPER_API_KEY",     "test-serper-key")
os.environ.setdefault("GOOGLE_CSE_API_KEY", "test-cse-key")
os.environ.setdefault("GOOGLE_CSE_CX",      "test-cx-id")

# ── Now import modules under test ────────────────────────────────────────────
import config  # noqa: E402 — must come after env var setup

# Load config without SystemExit (all keys are set above)
config.load_and_validate()

from tools import reverse_search, upload_history, fact_check, web_search_fetch  # noqa: E402


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────

def _make_httpx_response(status: int, body: dict | str) -> MagicMock:
    """Build a mock httpx Response object."""
    resp = MagicMock()
    resp.status_code = status
    if isinstance(body, dict):
        resp.json.return_value = body
        resp.text = json.dumps(body)
    else:
        resp.json.side_effect = ValueError("not json")
        resp.text = body
    # raise_for_status raises only on 4xx/5xx
    if status >= 400:
        import httpx
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            message=f"HTTP {status}",
            request=MagicMock(),
            response=resp,
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


# ────────────────────────────────────────────────────────────────────────────
# 1. reverse_search_frame
# ────────────────────────────────────────────────────────────────────────────

class TestReverseSearchFrame(unittest.TestCase):

    _VALID_ARGS = {
        "image":   "https://example.com/frame.jpg",
        "case_id": "case-001",
    }

    _CSE_RESPONSE = {
        "items": [
            {
                "link":    "https://news.example.com/article1",
                "snippet": "2023-01-15 — Frame appeared in breaking news coverage …",
            },
            {
                "link":    "https://social.example.com/post/42",
                "snippet": "2022-12-01 — Earlier appearance on social media …",
            },
        ]
    }

    def _reset_rate_limiter(self):
        """Force the module-level rate-limiter window to reset."""
        reverse_search._window_start = 0.0
        reverse_search._window_count = 0

    def setUp(self):
        self._reset_rate_limiter()

    # ── Happy path ────────────────────────────────────────────────────────────

    @patch("tools.reverse_search.httpx.get")
    def test_happy_path_returns_matches(self, mock_get):
        mock_get.return_value = _make_httpx_response(200, self._CSE_RESPONSE)

        result = reverse_search.run(self._VALID_ARGS)

        self.assertNotIn("error", result)
        self.assertIn("matches", result)
        self.assertIn("match_count", result)
        self.assertIn("case_id", result)
        self.assertEqual(result["case_id"], "case-001")
        self.assertIsInstance(result["matches"], list)
        self.assertEqual(result["match_count"], 2)
        for m in result["matches"]:
            self.assertIn("source_url", m)
            self.assertIn("first_seen_date", m)
            self.assertIn("similarity_score", m)

    @patch("tools.reverse_search.httpx.get")
    def test_empty_results_still_valid_schema(self, mock_get):
        mock_get.return_value = _make_httpx_response(200, {"items": []})
        result = reverse_search.run(self._VALID_ARGS)
        self.assertNotIn("error", result)
        self.assertEqual(result["match_count"], 0)
        self.assertEqual(result["matches"], [])

    # ── Invalid input ─────────────────────────────────────────────────────────

    def test_missing_image_returns_structured_error(self):
        result = reverse_search.run({"case_id": "case-001"})
        self.assertTrue(result.get("error"))
        self.assertIn("reason", result)
        self.assertIn("case_id", result)

    def test_missing_case_id_returns_structured_error(self):
        result = reverse_search.run({"image": "https://example.com/frame.jpg"})
        self.assertTrue(result.get("error"))
        self.assertIn("reason", result)

    def test_empty_case_id_returns_structured_error(self):
        result = reverse_search.run({"image": "https://example.com/f.jpg", "case_id": "  "})
        self.assertTrue(result.get("error"))

    # ── Rate-limit exhaustion ─────────────────────────────────────────────────

    def test_rate_limit_returns_structured_error(self):
        # Exhaust the window counter manually
        reverse_search._window_count = config.REVERSE_SEARCH_RATE_LIMIT
        reverse_search._window_start = __import__("time").monotonic()

        result = reverse_search.run(self._VALID_ARGS)
        self.assertTrue(result.get("error"))
        self.assertEqual(result.get("reason"), "rate_limited")
        self.assertIn("retry_after_seconds", result)
        self.assertIsInstance(result["retry_after_seconds"], int)
        self.assertIn("case_id", result)

    # ── Transient failure with retry exhaustion ───────────────────────────────

    @patch("tools.reverse_search.httpx.get")
    @patch("tools.reverse_search.time.sleep", return_value=None)  # no real sleeps
    def test_all_retries_exhausted_returns_structured_error(self, mock_sleep, mock_get):
        import httpx
        mock_get.side_effect = httpx.TimeoutException("timed out")

        result = reverse_search.run(self._VALID_ARGS)
        self.assertTrue(result.get("error"))
        self.assertIn("All retries exhausted", result["reason"])
        self.assertIn("case_id", result)
        # Should have retried MAX_RETRIES+1 times total
        self.assertEqual(mock_get.call_count, config.MAX_RETRIES + 1)

    # ── 4xx non-429 → no retry ────────────────────────────────────────────────

    @patch("tools.reverse_search.httpx.get")
    def test_403_client_error_no_retry(self, mock_get):
        mock_get.return_value = _make_httpx_response(403, "Forbidden")
        result = reverse_search.run(self._VALID_ARGS)
        self.assertTrue(result.get("error"))
        self.assertIn("403", result["reason"])
        self.assertEqual(mock_get.call_count, 1)  # called exactly once, no retry


# ────────────────────────────────────────────────────────────────────────────
# 2. check_upload_history
# ────────────────────────────────────────────────────────────────────────────

class TestCheckUploadHistory(unittest.TestCase):

    _VALID_ARGS = {
        "video_url_or_id": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "case_id": "case-002",
    }

    _VIDEO_RESPONSE = {
        "items": [{
            "snippet": {
                "publishedAt":  "2009-10-25T06:57:33Z",
                "channelTitle": "Rick Astley",
                "channelId":    "UCuAXFkgsw1L7xaCfnd5JJOw",
                "title":        "Rick Astley - Never Gonna Give You Up (Official Music Video)",
            }
        }]
    }

    _CHANNEL_RESPONSE = {
        "items": [{
            "snippet": {"publishedAt": "2006-03-01T00:00:00Z"}
        }]
    }

    _SEARCH_RESPONSE = {
        "items": [
            {"id": {"videoId": "abc1234abcd"}},
            {"id": {"videoId": "dQw4w9WgXcQ"}},   # original — should be filtered
        ]
    }

    def _reset_rate_limiter(self):
        upload_history._window_start = 0.0
        upload_history._window_count = 0

    def setUp(self):
        self._reset_rate_limiter()

    # ── Happy path ────────────────────────────────────────────────────────────

    @patch("tools.upload_history.httpx.get")
    def test_happy_path_full_output_schema(self, mock_get):
        mock_get.side_effect = [
            _make_httpx_response(200, self._VIDEO_RESPONSE),
            _make_httpx_response(200, self._CHANNEL_RESPONSE),
            _make_httpx_response(200, self._SEARCH_RESPONSE),
        ]

        result = upload_history.run(self._VALID_ARGS)

        self.assertNotIn("error", result)
        self.assertIn("actual_upload_date", result)
        self.assertIn("channel_name", result)
        self.assertIn("channel_created_date", result)
        self.assertIn("prior_reuploads_found", result)
        self.assertIn("reupload_sources", result)
        self.assertIn("case_id", result)
        self.assertEqual(result["case_id"], "case-002")
        self.assertIsInstance(result["reupload_sources"], list)
        self.assertIsInstance(result["prior_reuploads_found"], bool)

    @patch("tools.upload_history.httpx.get")
    def test_bare_video_id_accepted(self, mock_get):
        mock_get.side_effect = [
            _make_httpx_response(200, self._VIDEO_RESPONSE),
            _make_httpx_response(200, self._CHANNEL_RESPONSE),
            _make_httpx_response(200, self._SEARCH_RESPONSE),
        ]
        args = {"video_url_or_id": "dQw4w9WgXcQ", "case_id": "case-002"}
        result = upload_history.run(args)
        self.assertNotIn("error", result)

    # ── Invalid input ─────────────────────────────────────────────────────────

    def test_missing_video_url_returns_structured_error(self):
        result = upload_history.run({"case_id": "case-002"})
        self.assertTrue(result.get("error"))
        self.assertIn("reason", result)

    def test_invalid_url_returns_structured_error(self):
        result = upload_history.run({
            "video_url_or_id": "not-a-youtube-url-###",
            "case_id": "case-002",
        })
        self.assertTrue(result.get("error"))
        self.assertIn("reason", result)

    # ── Rate limit ────────────────────────────────────────────────────────────

    def test_rate_limit_returns_structured_error(self):
        upload_history._window_count = config.UPLOAD_HISTORY_RATE_LIMIT
        upload_history._window_start = __import__("time").monotonic()

        result = upload_history.run(self._VALID_ARGS)
        self.assertTrue(result.get("error"))
        self.assertEqual(result.get("reason"), "rate_limited")
        self.assertIn("retry_after_seconds", result)

    # ── Video not found ───────────────────────────────────────────────────────

    @patch("tools.upload_history.httpx.get")
    def test_video_not_found_returns_structured_error(self, mock_get):
        mock_get.return_value = _make_httpx_response(200, {"items": []})
        result = upload_history.run(self._VALID_ARGS)
        self.assertTrue(result.get("error"))
        self.assertIn("No YouTube video found", result["reason"])


# ────────────────────────────────────────────────────────────────────────────
# 3. fact_check_claim
# ────────────────────────────────────────────────────────────────────────────

class TestFactCheckClaim(unittest.TestCase):

    _VALID_ARGS = {
        "claim_text": "The Eiffel Tower is located in London.",
        "case_id":    "case-003",
    }

    _FC_RESPONSE_FALSE = {
        "claims": [{
            "claimReview": [{
                "textualRating": "False",
                "publisher": {"name": "Snopes"},
                "url": "https://snopes.com/eiffel-tower-london",
            }]
        }]
    }

    _FC_RESPONSE_EMPTY = {"claims": []}

    def _reset_rate_limiter(self):
        fact_check._window_start = 0.0
        fact_check._window_count = 0

    def setUp(self):
        self._reset_rate_limiter()

    # ── Happy path ────────────────────────────────────────────────────────────

    @patch("tools.fact_check.httpx.get")
    def test_happy_path_false_verdict(self, mock_get):
        mock_get.return_value = _make_httpx_response(200, self._FC_RESPONSE_FALSE)

        result = fact_check.run(self._VALID_ARGS)

        self.assertNotIn("error", result)
        self.assertIn("verdict", result)
        self.assertIn("matched_factchecks", result)
        self.assertIn("case_id", result)
        self.assertEqual(result["case_id"], "case-003")
        self.assertIn(result["verdict"], ("true", "false", "misleading", "unverified"))
        self.assertEqual(result["verdict"], "false")
        self.assertIsInstance(result["matched_factchecks"], list)
        for fc in result["matched_factchecks"]:
            self.assertIn("source", fc)
            self.assertIn("url", fc)
            self.assertIn("rating", fc)

    @patch("tools.fact_check.httpx.get")
    def test_empty_results_returns_unverified(self, mock_get):
        mock_get.return_value = _make_httpx_response(200, self._FC_RESPONSE_EMPTY)
        result = fact_check.run(self._VALID_ARGS)
        self.assertNotIn("error", result)
        self.assertEqual(result["verdict"], "unverified")
        self.assertEqual(result["matched_factchecks"], [])

    # ── Invalid input ─────────────────────────────────────────────────────────

    def test_missing_claim_text_returns_structured_error(self):
        result = fact_check.run({"case_id": "case-003"})
        self.assertTrue(result.get("error"))
        self.assertIn("reason", result)

    def test_claim_too_long_returns_structured_error(self):
        result = fact_check.run({
            "claim_text": "x" * 1001,
            "case_id":    "case-003",
        })
        self.assertTrue(result.get("error"))
        self.assertIn("1000", result["reason"])

    # ── Rate limit ────────────────────────────────────────────────────────────

    def test_rate_limit_returns_structured_error(self):
        fact_check._window_count = config.FACT_CHECK_RATE_LIMIT
        fact_check._window_start = __import__("time").monotonic()

        result = fact_check.run(self._VALID_ARGS)
        self.assertTrue(result.get("error"))
        self.assertEqual(result.get("reason"), "rate_limited")
        self.assertIn("retry_after_seconds", result)
        self.assertIn("case_id", result)

    # ── All retries exhausted ─────────────────────────────────────────────────

    @patch("tools.fact_check.httpx.get")
    @patch("tools.fact_check.time.sleep", return_value=None)
    def test_timeout_retries_then_error(self, mock_sleep, mock_get):
        import httpx
        mock_get.side_effect = httpx.TimeoutException("timeout")
        result = fact_check.run(self._VALID_ARGS)
        self.assertTrue(result.get("error"))
        self.assertIn("All retries exhausted", result["reason"])
        self.assertEqual(mock_get.call_count, config.MAX_RETRIES + 1)


# ────────────────────────────────────────────────────────────────────────────
# 4. web_search_fetch
# ────────────────────────────────────────────────────────────────────────────

class TestWebSearchFetch(unittest.TestCase):

    _SEARCH_ARGS = {
        "query":   "Chorus video analytics pipeline",
        "case_id": "case-004",
        "mode":    "search",
    }

    _FETCH_ARGS = {
        "url":     "https://example.com/article",
        "case_id": "case-004",
        "mode":    "fetch",
    }

    _SERPER_RESPONSE = {
        "organic": [
            {
                "title":   "Chorus Video Pipeline",
                "link":    "https://github.com/d-khush06/Chorus",
                "snippet": "Multi-agent video analytics pipeline …",
            }
        ]
    }

    def _reset_rate_limiter(self):
        web_search_fetch._window_start = 0.0
        web_search_fetch._window_count = 0

    def setUp(self):
        self._reset_rate_limiter()

    # ── Happy path: search mode ───────────────────────────────────────────────

    @patch("tools.web_search_fetch.httpx.post")
    def test_search_mode_happy_path(self, mock_post):
        mock_post.return_value = _make_httpx_response(200, self._SERPER_RESPONSE)

        result = web_search_fetch.run(self._SEARCH_ARGS)

        self.assertNotIn("error", result)
        self.assertIn("results", result)
        self.assertIn("case_id", result)
        self.assertEqual(result["case_id"], "case-004")
        self.assertIsInstance(result["results"], list)
        for r in result["results"]:
            self.assertIn("title", r)
            self.assertIn("url", r)
            self.assertIn("snippet", r)

    # ── Happy path: fetch mode ────────────────────────────────────────────────

    @patch("tools.web_search_fetch.httpx.get")
    def test_fetch_mode_happy_path(self, mock_get):
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status.return_value = None
        resp.headers = {"content-type": "text/html"}
        resp.text = "<html><head><title>T</title></head><body><p>Hello world</p></body></html>"
        resp.url = "https://example.com/article"
        mock_get.return_value = resp

        result = web_search_fetch.run(self._FETCH_ARGS)

        self.assertNotIn("error", result)
        self.assertIn("content", result)
        self.assertIn("url", result)
        self.assertIn("case_id", result)
        self.assertEqual(result["case_id"], "case-004")
        self.assertIn("Hello world", result["content"])

    # ── Invalid input ─────────────────────────────────────────────────────────

    def test_invalid_mode_returns_structured_error(self):
        result = web_search_fetch.run({
            "query":   "test",
            "case_id": "case-004",
            "mode":    "INVALID",
        })
        self.assertTrue(result.get("error"))
        self.assertIn("reason", result)

    def test_fetch_mode_missing_url_returns_structured_error(self):
        result = web_search_fetch.run({
            "case_id": "case-004",
            "mode":    "fetch",
        })
        self.assertTrue(result.get("error"))

    def test_fetch_mode_non_http_url_returns_structured_error(self):
        result = web_search_fetch.run({
            "url":     "ftp://example.com/data",
            "case_id": "case-004",
            "mode":    "fetch",
        })
        self.assertTrue(result.get("error"))
        self.assertIn("https", result["reason"])

    def test_search_mode_missing_query_returns_structured_error(self):
        result = web_search_fetch.run({"case_id": "case-004", "mode": "search"})
        self.assertTrue(result.get("error"))

    # ── Rate limit ────────────────────────────────────────────────────────────

    def test_rate_limit_returns_structured_error(self):
        web_search_fetch._window_count = config.WEB_SEARCH_RATE_LIMIT
        web_search_fetch._window_start = __import__("time").monotonic()

        result = web_search_fetch.run(self._SEARCH_ARGS)
        self.assertTrue(result.get("error"))
        self.assertEqual(result.get("reason"), "rate_limited")
        self.assertIn("retry_after_seconds", result)
        self.assertIn("case_id", result)

    # ── Transient 5xx → retries → error ──────────────────────────────────────

    @patch("tools.web_search_fetch.httpx.post")
    @patch("tools.web_search_fetch.time.sleep", return_value=None)
    def test_server_error_retries_then_error(self, mock_sleep, mock_post):
        mock_post.return_value = _make_httpx_response(500, "Internal Server Error")
        result = web_search_fetch.run(self._SEARCH_ARGS)
        self.assertTrue(result.get("error"))
        self.assertIn("All retries exhausted", result["reason"])
        self.assertEqual(mock_post.call_count, config.MAX_RETRIES + 1)

    # ── 4xx non-429 → no retry ────────────────────────────────────────────────

    @patch("tools.web_search_fetch.httpx.post")
    def test_401_no_retry(self, mock_post):
        mock_post.return_value = _make_httpx_response(401, "Unauthorized")
        result = web_search_fetch.run(self._SEARCH_ARGS)
        self.assertTrue(result.get("error"))
        self.assertIn("401", result["reason"])
        self.assertEqual(mock_post.call_count, 1)


# ────────────────────────────────────────────────────────────────────────────
# case_id passthrough — cross-tool assertion
# ────────────────────────────────────────────────────────────────────────────

class TestCaseIdPassthrough(unittest.TestCase):
    """Every tool output (success or error) must include the case_id."""

    def setUp(self):
        for mod in (reverse_search, upload_history, fact_check, web_search_fetch):
            mod._window_start = 0.0
            mod._window_count = 0

    def test_reverse_search_error_includes_case_id(self):
        result = reverse_search.run({"case_id": "PASS-THROUGH"})
        # image missing → validation error
        self.assertEqual(result.get("case_id"), "PASS-THROUGH")

    def test_upload_history_error_includes_case_id(self):
        result = upload_history.run({"case_id": "PASS-THROUGH"})
        self.assertEqual(result.get("case_id"), "PASS-THROUGH")

    def test_fact_check_error_includes_case_id(self):
        result = fact_check.run({"case_id": "PASS-THROUGH"})
        self.assertEqual(result.get("case_id"), "PASS-THROUGH")

    def test_web_search_error_includes_case_id(self):
        result = web_search_fetch.run({"case_id": "PASS-THROUGH", "mode": "search"})
        self.assertEqual(result.get("case_id"), "PASS-THROUGH")


# ────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
