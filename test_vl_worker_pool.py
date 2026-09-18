"""
test_vl_worker_pool.py — Unit Tests for process_playlist() Worker Pool
=======================================================================
All tests run WITHOUT a real GPU or model.
The vLLM engine and project_manager are fully mocked.

Test matrix
-----------
  test_semaphore_cap          — max_concurrent=3 with 10 videos: never > 3 in-flight
  test_failure_isolation      — 1 of 10 deliberately fails; other 9 complete successfully
  test_order_preservation     — mock resolves out-of-order; results match input order
  test_add_artifact_per_video — add_artifact called exactly once per video (success + fail)

Run
---
  python -m pytest test_vl_worker_pool.py -v
  python test_vl_worker_pool.py          # also works directly
"""

import asyncio
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch, call
import json

# ─────────────────────────────────────────────────────────────────────────────
# SETUP — patch vLLM and project_manager BEFORE importing run_vl_agent
# ─────────────────────────────────────────────────────────────────────────────

# Mock vllm so the import doesn't require the real package
_mock_vllm = MagicMock()
sys.modules.setdefault("vllm", _mock_vllm)
sys.modules.setdefault("vllm.engine", MagicMock())
sys.modules.setdefault("torch", MagicMock())
sys.modules.setdefault("transformers", MagicMock())
sys.modules.setdefault("qwen_vl_utils", MagicMock())
sys.modules.setdefault("cv2", MagicMock())

# We will inject a mock project_manager into run_vl_agent's namespace each test
_mock_pm = MagicMock()
_mock_pm.add_artifact = MagicMock(return_value="leaf_hash_mock")
sys.modules["project_manager"] = _mock_pm


# ─────────────────────────────────────────────────────────────────────────────
# MOCK FACTORY
# ─────────────────────────────────────────────────────────────────────────────

def _make_mock_analyze(
    n_videos: int,
    fail_indices: set = None,
    delays: dict = None,
):
    """
    Return an AsyncMock for analyze_video_async that:
      - Tracks concurrent call count (for semaphore cap test)
      - Optionally raises for specified video indices (failure isolation test)
      - Optionally applies asyncio.sleep delays per index (order preservation test)

    The mock identifies which video it's handling by case_id (which encodes the index
    as 'case_<idx>').
    """
    fail_indices  = fail_indices  or set()
    delays        = delays        or {}
    active_count  = {"value": 0}   # shared mutable counter
    peak_active   = {"value": 0}   # max concurrent calls observed

    async def _mock_analyze(video_frames_or_path, case_id, user_prompt="", metadata=None):
        # Extract index from case_id (format: "case_<idx>")
        idx = int(case_id.split("_")[1])

        active_count["value"] += 1
        peak_active["value"]   = max(peak_active["value"], active_count["value"])

        try:
            delay = delays.get(idx, 0.01)   # default 10ms per video
            await asyncio.sleep(delay)

            if idx in fail_indices:
                raise RuntimeError(f"Deliberate failure for video {idx}")

            return {"video_index": idx, "case_id": case_id, "raw_output": f"analysis of video {idx}"}

        finally:
            active_count["value"] -= 1

    return _mock_analyze, active_count, peak_active


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _make_video_list(n: int) -> tuple:
    """Return (video_list, case_ids) for n videos."""
    video_list = [{"path": f"dummy_{i}.mp4", "user_prompt": "test"} for i in range(n)]
    case_ids   = [f"case_{i}" for i in range(n)]
    return video_list, case_ids


async def _run_playlist(mock_analyze, video_list, case_ids, max_concurrent):
    """
    Run process_playlist with the given mock patched into run_vl_agent,
    engine pre-set to a truthy sentinel, and project_manager mocked.
    """
    import run_vl_agent as agent

    # Inject a dummy engine so the "engine is None" guard passes
    original_engine = agent._vl_engine
    agent._vl_engine = object()   # truthy sentinel

    # Reset add_artifact call log before each run
    _mock_pm.add_artifact.reset_mock()

    try:
        with patch.object(agent, "analyze_video_async", side_effect=mock_analyze):
            results = await agent.process_playlist(video_list, case_ids, max_concurrent)
    finally:
        agent._vl_engine = original_engine

    return results


# ─────────────────────────────────────────────────────────────────────────────
# TEST CASES
# ─────────────────────────────────────────────────────────────────────────────

class TestProcessPlaylist(unittest.IsolatedAsyncioTestCase):

    # ── Test 1: Semaphore cap ─────────────────────────────────────────────────
    async def test_semaphore_cap(self):
        """
        process_playlist with max_concurrent=3 against 10 mock videos must
        never have more than 3 concurrent analyze_video_async calls active at once.
        """
        n, max_c = 10, 3
        video_list, case_ids = _make_video_list(n)

        # All videos take 50ms so some overlap is guaranteed
        delays = {i: 0.05 for i in range(n)}
        mock_fn, active_count, peak_active = _make_mock_analyze(n, delays=delays)

        results = await _run_playlist(mock_fn, video_list, case_ids, max_concurrent=max_c)

        self.assertEqual(len(results), n, "Should return exactly one result per video")
        self.assertLessEqual(
            peak_active["value"],
            max_c,
            f"Peak concurrent calls {peak_active['value']} exceeded max_concurrent={max_c}",
        )
        print(f"  [✓] Peak concurrent calls: {peak_active['value']} (limit={max_c})")

    # ── Test 2: Failure isolation ─────────────────────────────────────────────
    async def test_failure_isolation(self):
        """
        One deliberately failing video must not prevent the other 9 from completing.
        The failing slot must have status='failed', others must not.
        """
        n = 10
        fail_idx = 4   # video index 4 will raise RuntimeError
        video_list, case_ids = _make_video_list(n)

        mock_fn, _, _ = _make_mock_analyze(n, fail_indices={fail_idx})
        results = await _run_playlist(mock_fn, video_list, case_ids, max_concurrent=3)

        self.assertEqual(len(results), n)

        # The failing slot
        self.assertEqual(
            results[fail_idx].get("status"), "failed",
            f"results[{fail_idx}] should be a failure record"
        )
        self.assertIn("error", results[fail_idx])

        # All other slots must be successful
        for i, r in enumerate(results):
            if i == fail_idx:
                continue
            self.assertNotEqual(
                r.get("status"), "failed",
                f"results[{i}] should have succeeded but got: {r}"
            )
            self.assertEqual(r.get("video_index"), i)

        print(f"  [✓] 9/10 succeeded, video {fail_idx} correctly isolated as failed")

    # ── Test 3: Order preservation ────────────────────────────────────────────
    async def test_order_preservation(self):
        """
        Results must be in input order even when mock completions are out of order.
        We make video 3 finish first (0ms delay) and video 0 finish last (150ms).
        """
        n = 5
        video_list, case_ids = _make_video_list(n)

        # Deliberately reversed delays: last video finishes first
        delays = {
            0: 0.15,   # slowest — finishes last
            1: 0.10,
            2: 0.07,
            3: 0.00,   # fastest — finishes first
            4: 0.05,
        }
        mock_fn, _, _ = _make_mock_analyze(n, delays=delays)
        results = await _run_playlist(mock_fn, video_list, case_ids, max_concurrent=n)

        self.assertEqual(len(results), n)
        for i, r in enumerate(results):
            self.assertIsNotNone(r, f"results[{i}] should not be None")
            self.assertEqual(
                r.get("video_index"), i,
                f"results[{i}].video_index={r.get('video_index')} — order not preserved"
            )

        print(f"  [✓] All {n} results in correct input order despite out-of-order completion")

    # ── Test 4: add_artifact called exactly once per video ───────────────────
    async def test_add_artifact_per_video(self):
        """
        project_manager.add_artifact must be called exactly once per video —
        with the correct case_id — for both success and failure cases.
        """
        n = 10
        fail_idx = 7
        video_list, case_ids = _make_video_list(n)

        mock_fn, _, _ = _make_mock_analyze(n, fail_indices={fail_idx})
        results = await _run_playlist(mock_fn, video_list, case_ids, max_concurrent=4)

        self.assertEqual(len(results), n)

        # add_artifact should be called exactly n times total
        actual_call_count = _mock_pm.add_artifact.call_count
        self.assertEqual(
            actual_call_count,
            n,
            f"add_artifact called {actual_call_count} times, expected {n}",
        )

        # Verify each call used the correct case_id and artifact_name
        called_case_ids = {c.args[0] for c in _mock_pm.add_artifact.call_args_list}
        expected_case_ids = set(case_ids)
        self.assertEqual(
            called_case_ids,
            expected_case_ids,
            f"add_artifact called with unexpected case_ids: {called_case_ids - expected_case_ids}",
        )

        # Verify artifact_name is "vision_analysis" for every call
        for c in _mock_pm.add_artifact.call_args_list:
            self.assertEqual(
                c.args[1],
                "vision_analysis",
                f"Expected artifact_name='vision_analysis', got '{c.args[1]}'",
            )

        # Verify the failure slot was persisted with status=failed
        fail_case_id = case_ids[fail_idx]
        fail_call = next(
            (c for c in _mock_pm.add_artifact.call_args_list if c.args[0] == fail_case_id),
            None,
        )
        self.assertIsNotNone(fail_call, f"add_artifact never called for failing case {fail_case_id}")
        fail_artifact_bytes = fail_call.args[2]
        fail_artifact_dict  = json.loads(fail_artifact_bytes.decode("utf-8"))
        self.assertEqual(fail_artifact_dict.get("status"), "failed")

        print(
            f"  [✓] add_artifact called exactly {n} times — "
            f"all correct case_ids, failure slot persisted with status='failed'"
        )


# ─────────────────────────────────────────────────────────────────────────────
# ADDITIONAL EDGE CASE TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestProcessPlaylistEdgeCases(unittest.IsolatedAsyncioTestCase):

    async def test_mismatched_lengths_raises(self):
        """video_list and case_ids of different lengths must raise ValueError."""
        import run_vl_agent as agent
        original_engine = agent._vl_engine
        agent._vl_engine = object()
        try:
            with self.assertRaises(ValueError):
                await agent.process_playlist(
                    video_list=[{"path": "a.mp4"}],
                    case_ids=["id1", "id2"],     # wrong length
                    max_concurrent=1,
                )
        finally:
            agent._vl_engine = original_engine

    async def test_no_engine_raises(self):
        """process_playlist with no engine running must raise RuntimeError."""
        import run_vl_agent as agent
        original_engine = agent._vl_engine
        agent._vl_engine = None
        try:
            with self.assertRaises(RuntimeError):
                await agent.process_playlist(
                    video_list=[{"path": "a.mp4"}],
                    case_ids=["id1"],
                    max_concurrent=1,
                )
        finally:
            agent._vl_engine = original_engine

    async def test_single_video_playlist(self):
        """A one-video playlist should work identically to the multi-video case."""
        video_list, case_ids = _make_video_list(1)
        mock_fn, _, _ = _make_mock_analyze(1)
        results = await _run_playlist(mock_fn, video_list, case_ids, max_concurrent=1)
        self.assertEqual(len(results), 1)
        self.assertNotEqual(results[0].get("status"), "failed")

    async def test_all_failures_still_returns_full_list(self):
        """If every video fails, we must still get a full-length list of failure records."""
        n = 5
        video_list, case_ids = _make_video_list(n)
        mock_fn, _, _ = _make_mock_analyze(n, fail_indices=set(range(n)))
        results = await _run_playlist(mock_fn, video_list, case_ids, max_concurrent=2)
        self.assertEqual(len(results), n)
        for r in results:
            self.assertEqual(r.get("status"), "failed")


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
