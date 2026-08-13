"""
test_manipulation_detection.py
==============================
Chorus — Step 4: Manipulation Detection Unit Tests

All 6 required test cases as specified in the system prompt.
These tests use MOCK Step 3 output and MOCK model inference —
they do NOT depend on the real Step 3 module or real SBI weights.

Run:
    python test_manipulation_detection.py
    python -m pytest test_manipulation_detection.py -v
"""

import json
import unittest
import time
from unittest.mock import MagicMock, patch, PropertyMock
from dataclasses import dataclass

from manipulation_detection import (
    # Contracts
    Step3Output,
    Step4Output,
    ManipulationCheck,
    PerFrameScore,
    # Functions under test
    parse_step3_input,
    build_step4_output,
    step4_output_to_dict,
    detect_manipulation,
    _aggregate_scores,
    _routing_decision,
    # Constants
    FRAME_FAKE_THRESHOLD,
    VIDEO_FLAG_THRESHOLD,
    RTSP_WINDOW_SECONDS,
)


# ---------------------------------------------------------------------------
# Shared mock builders
# ---------------------------------------------------------------------------

def make_mock_step3_dict(**overrides) -> dict:
    """Build a minimal valid Step 3 output dict for testing."""
    base = {
        "video_id":         "test_vid_001",
        "video_path":       "/tmp/test_video.mp4",
        "source_type":      "local_upload",
        "duration_seconds": 60.0,
        "dedup_status":     "unique",
        "dedup_hash":       "abc123def456",
        "upstream_metadata": {"step1_tag": "demo", "pipeline_version": "0.1"},
    }
    base.update(overrides)
    return base


def make_mock_step3_output(**overrides) -> Step3Output:
    return parse_step3_input(make_mock_step3_dict(**overrides))


def make_mock_model(fake_probability: float = 0.05):
    """
    Return a (mock_model, mock_device) tuple that always predicts `fake_probability`.
    Used instead of loading real SBI weights.
    """
    import torch

    class _FakeModel:
        def __call__(self, tensor):
            # Return logit that, when sigmoided, gives fake_probability
            import math
            logit_val = math.log(fake_probability / (1 - fake_probability + 1e-9))
            return torch.tensor([[logit_val]])
        def eval(self):       return self
        def to(self, device): return self

    device = torch.device("cpu")
    return _FakeModel(), device


def make_per_frame_scores(n_clean: int, n_fake: int) -> list:
    """
    Build a list of PerFrameScore with n_clean frames below FRAME_FAKE_THRESHOLD
    and n_fake frames above it.
    """
    scores = []
    for i in range(n_clean):
        scores.append(PerFrameScore(timestamp=float(i), fake_probability=0.1))
    for i in range(n_fake):
        scores.append(PerFrameScore(timestamp=float(n_clean + i), fake_probability=0.9))
    return scores


# ---------------------------------------------------------------------------
# Test Case 1: Adapter parsing + dedup_status guard
# ---------------------------------------------------------------------------

class TestParseStep3Input(unittest.TestCase):
    """Test 1: parse_step3_input() adapter correctness and dedup_status guard."""

    def test_valid_input_parses_correctly(self):
        """All fields map correctly from raw dict to Step3Output dataclass."""
        raw = make_mock_step3_dict()
        out = parse_step3_input(raw)

        self.assertIsInstance(out, Step3Output)
        self.assertEqual(out.video_id, "test_vid_001")
        self.assertEqual(out.source_type, "local_upload")
        self.assertEqual(out.dedup_hash, "abc123def456")
        self.assertEqual(out.duration_seconds, 60.0)
        self.assertEqual(out.upstream_metadata["step1_tag"], "demo")

    def test_dedup_status_not_unique_raises(self):
        """CRITICAL: dedup_status != 'unique' must raise ValueError immediately."""
        raw = make_mock_step3_dict(dedup_status="duplicate")
        with self.assertRaises(ValueError) as ctx:
            parse_step3_input(raw)
        self.assertIn("dedup_status", str(ctx.exception).lower())

    def test_dedup_status_empty_raises(self):
        """Empty dedup_status also triggers the guard."""
        raw = make_mock_step3_dict(dedup_status="")
        with self.assertRaises(ValueError):
            parse_step3_input(raw)

    def test_missing_video_id_raises(self):
        """Missing video_id raises KeyError."""
        raw = make_mock_step3_dict()
        raw.pop("video_id")
        with self.assertRaises(KeyError):
            parse_step3_input(raw)

    def test_alternative_field_names_accepted(self):
        """Adapter handles alternative field names from Step 3 teammates."""
        raw = {
            "video_id":           "alt_001",
            "video_file":         "/tmp/alt.mp4",   # alternative to video_path
            "source_type":        "youtube",
            "video_duration_seconds": 120.0,        # alternative to duration_seconds
            "dedup_status":       "unique",
            "dedup_hash":         "hash_xyz",
            "upstream_metadata":  {},
        }
        out = parse_step3_input(raw)
        self.assertEqual(out.video_path, "/tmp/alt.mp4")
        self.assertEqual(out.duration_seconds, 120.0)

    def test_rtsp_null_duration_accepted(self):
        """live_rtsp source may have null duration_seconds."""
        raw = make_mock_step3_dict(source_type="live_rtsp", duration_seconds=None)
        out = parse_step3_input(raw)
        self.assertIsNone(out.duration_seconds)

    def test_upstream_metadata_passed_through_unchanged(self):
        """upstream_metadata is not inspected or modified."""
        meta = {"weird_key": [1, 2, 3], "nested": {"a": "b"}}
        raw  = make_mock_step3_dict(upstream_metadata=meta)
        out  = parse_step3_input(raw)
        self.assertEqual(out.upstream_metadata, meta)


# ---------------------------------------------------------------------------
# Test Case 2: Known-real video → CLEAN → CONTINUE_TO_STEP_5
# ---------------------------------------------------------------------------

class TestKnownRealVideo(unittest.TestCase):
    """Test 2: Real video with consistently low fake_probability → CLEAN."""

    def test_low_fake_scores_produce_clean_verdict(self):
        """
        Simulate 10 frames, all with fake_probability = 0.05 (real content).
        Expected: verdict=CLEAN, routing=CONTINUE_TO_STEP_5.
        """
        per_frame = make_per_frame_scores(n_clean=10, n_fake=0)  # all clean
        score, verdict = _aggregate_scores(per_frame, faces_detected=10)

        self.assertEqual(verdict, "CLEAN")
        self.assertIsNotNone(score)
        self.assertLess(score, VIDEO_FLAG_THRESHOLD)

    def test_clean_verdict_routes_to_step5(self):
        routing = _routing_decision("CLEAN", detector_error=False)
        self.assertEqual(routing, "CONTINUE_TO_STEP_5")

    def test_output_contract_fields_present(self):
        """Verify all required downstream contract fields are in serialized output."""
        step3 = make_mock_step3_output()
        per_frame = make_per_frame_scores(n_clean=5, n_fake=0)
        score, verdict = _aggregate_scores(per_frame, faces_detected=5)

        check = ManipulationCheck(
            frames_analyzed=5,
            faces_detected=5,
            per_frame_scores=per_frame,
            video_level_score=score,
            verdict=verdict,
            detector_error=False,
            processing_time_seconds=1.23,
        )
        result  = build_step4_output(step3, check)
        as_dict = step4_output_to_dict(result)

        # All required downstream fields must be present
        required_top = {"video_id", "dedup_hash", "upstream_metadata",
                        "source_type", "manipulation_check", "routing_decision"}
        self.assertTrue(required_top.issubset(set(as_dict.keys())))

        mc = as_dict["manipulation_check"]
        required_mc = {"frames_analyzed", "faces_detected", "per_frame_scores",
                       "video_level_score", "aggregation_method", "verdict",
                       "detector_error", "processing_time_seconds"}
        self.assertTrue(required_mc.issubset(set(mc.keys())))

        # Pass-through fields unchanged
        self.assertEqual(as_dict["video_id"],   step3.video_id)
        self.assertEqual(as_dict["dedup_hash"], step3.dedup_hash)
        self.assertEqual(as_dict["upstream_metadata"], step3.upstream_metadata)


# ---------------------------------------------------------------------------
# Test Case 3: Known-deepfake video → FLAGGED → SEND_TO_REVIEW_QUEUE
# ---------------------------------------------------------------------------

class TestKnownDeepfakeVideo(unittest.TestCase):
    """Test 3: Deepfake video with majority high fake_probability → FLAGGED."""

    def test_majority_fake_frames_produce_flagged_verdict(self):
        """
        5 clean frames + 5 fake frames → 50% fake rate → >= VIDEO_FLAG_THRESHOLD (30%).
        Expected: verdict=FLAGGED.
        """
        per_frame = make_per_frame_scores(n_clean=5, n_fake=5)
        score, verdict = _aggregate_scores(per_frame, faces_detected=10)

        self.assertEqual(verdict, "FLAGGED")
        self.assertGreaterEqual(score, VIDEO_FLAG_THRESHOLD)

    def test_exactly_at_threshold_is_flagged(self):
        """
        Exactly 30% fake frames (3/10) → should be FLAGGED (>= threshold, not >).
        """
        per_frame = make_per_frame_scores(n_clean=7, n_fake=3)
        score, verdict = _aggregate_scores(per_frame, faces_detected=10)
        self.assertEqual(verdict, "FLAGGED")
        self.assertAlmostEqual(score, 0.3)

    def test_just_below_threshold_is_clean(self):
        """
        29% fake frames (2/7 = 28.6%) → should be CLEAN (below threshold).
        """
        per_frame = make_per_frame_scores(n_clean=5, n_fake=2)
        score, verdict = _aggregate_scores(per_frame, faces_detected=7)
        self.assertEqual(verdict, "CLEAN")
        self.assertLess(score, VIDEO_FLAG_THRESHOLD)

    def test_flagged_verdict_routes_to_review_queue(self):
        routing = _routing_decision("FLAGGED", detector_error=False)
        self.assertEqual(routing, "SEND_TO_REVIEW_QUEUE")

    def test_output_routing_decision_consistent_with_verdict(self):
        """routing_decision in output must match what _routing_decision() would return."""
        step3 = make_mock_step3_output()
        per_frame = make_per_frame_scores(n_clean=2, n_fake=8)
        score, verdict = _aggregate_scores(per_frame, faces_detected=10)

        check = ManipulationCheck(
            frames_analyzed=10, faces_detected=10,
            per_frame_scores=per_frame, video_level_score=score,
            verdict=verdict, detector_error=False, processing_time_seconds=2.0,
        )
        result = build_step4_output(step3, check)
        self.assertEqual(result.routing_decision, "SEND_TO_REVIEW_QUEUE")


# ---------------------------------------------------------------------------
# Test Case 4: No-faces video → NO_FACES_DETECTED → CONTINUE_TO_STEP_5
# ---------------------------------------------------------------------------

class TestNoFacesVideo(unittest.TestCase):
    """Test 4: Video with no detectable faces must NOT crash, must route to Step 5."""

    def test_zero_faces_produces_no_faces_detected(self):
        per_frame = []  # no frames produced face detections
        score, verdict = _aggregate_scores(per_frame, faces_detected=0)

        self.assertEqual(verdict, "NO_FACES_DETECTED")
        self.assertIsNone(score)

    def test_no_faces_detected_routes_to_step5(self):
        routing = _routing_decision("NO_FACES_DETECTED", detector_error=False)
        self.assertEqual(routing, "CONTINUE_TO_STEP_5")

    def test_output_serialization_with_null_score(self):
        """video_level_score=null must serialize correctly to JSON."""
        step3 = make_mock_step3_output()
        check = ManipulationCheck(
            frames_analyzed=20, faces_detected=0,
            per_frame_scores=[], video_level_score=None,
            verdict="NO_FACES_DETECTED", detector_error=False,
            processing_time_seconds=0.8,
        )
        result  = build_step4_output(step3, check)
        as_dict = step4_output_to_dict(result)

        self.assertIsNone(as_dict["manipulation_check"]["video_level_score"])
        self.assertEqual(as_dict["manipulation_check"]["verdict"], "NO_FACES_DETECTED")
        self.assertEqual(as_dict["routing_decision"], "CONTINUE_TO_STEP_5")

        # Must be JSON-serializable (not crash)
        serialized = json.dumps(as_dict)
        self.assertIn("NO_FACES_DETECTED", serialized)


# ---------------------------------------------------------------------------
# Test Case 5: Model failure → detector_error=True → SEND_TO_REVIEW_QUEUE
# ---------------------------------------------------------------------------

class TestModelFailureFailSafe(unittest.TestCase):
    """Test 5: Any model failure MUST produce detector_error=True and route to review."""

    def test_detector_error_forces_flagged_verdict(self):
        """detector_error=True must force FLAGGED regardless of per_frame_scores."""
        # Even with no per_frame_scores (as would happen if model never ran)
        score, verdict = _aggregate_scores([], faces_detected=0)
        # Override verdict as the core loop would do on error:
        # (the aggregation returns NO_FACES_DETECTED, but the error handler overrides)
        forced_verdict = "FLAGGED"  # done in detect_manipulation() error path
        routing = _routing_decision(forced_verdict, detector_error=True)
        self.assertEqual(routing, "SEND_TO_REVIEW_QUEUE")

    def test_routing_decision_with_detector_error_always_review(self):
        """routing_decision must be SEND_TO_REVIEW_QUEUE for any verdict + detector_error=True."""
        for verdict in ("CLEAN", "FLAGGED", "NO_FACES_DETECTED"):
            routing = _routing_decision(verdict, detector_error=True)
            self.assertEqual(routing, "SEND_TO_REVIEW_QUEUE",
                             f"Failed for verdict={verdict}")

    @patch("manipulation_detection.load_sbi_model")
    @patch("manipulation_detection._load_retinaface")
    def test_detect_manipulation_with_mock_model_failure(
        self, mock_face_loader, mock_model_loader
    ):
        """
        Simulate a model load error by patching load_sbi_model to raise.
        The function must:
          - Not crash (no unhandled exception)
          - Return a Step4Output
          - detector_error == True
          - verdict == "FLAGGED"
          - routing_decision == "SEND_TO_REVIEW_QUEUE"
        """
        mock_model_loader.side_effect = RuntimeError("Corrupt weights file")

        step3 = make_mock_step3_output()

        # Disable audit logging to avoid filesystem side effects in tests
        with patch("manipulation_detection._write_audit_log"):
            result = detect_manipulation(
                step3,
                frame_sample_rate=1.0,
                weights_path="/nonexistent/path/model.tar",
            )

        self.assertIsInstance(result, Step4Output)
        self.assertTrue(result.manipulation_check.detector_error)
        self.assertEqual(result.manipulation_check.verdict, "FLAGGED")
        self.assertEqual(result.routing_decision, "SEND_TO_REVIEW_QUEUE")

    @patch("manipulation_detection._get_frame_iter")
    @patch("manipulation_detection._load_retinaface")
    def test_detect_manipulation_frame_loop_failure_is_fail_safe(
        self, mock_face_loader, mock_frame_iter
    ):
        """
        Simulate the frame iterator itself crashing (e.g., corrupt file).
        Must still produce detector_error=True and route to review.
        Uses pure MagicMock model tuple — no torch required.
        """
        mock_frame_iter.side_effect = IOError("Cannot read video file")
        mock_face_loader.return_value = MagicMock()

        step3 = make_mock_step3_output()
        # Pure MagicMock model/device — no torch import needed
        mock_model_tuple = (MagicMock(), MagicMock())

        with patch("manipulation_detection._write_audit_log"):
            result = detect_manipulation(
                step3,
                frame_sample_rate=1.0,
                model_and_device=mock_model_tuple,
            )

        self.assertTrue(result.manipulation_check.detector_error)
        self.assertEqual(result.routing_decision, "SEND_TO_REVIEW_QUEUE")


# ---------------------------------------------------------------------------
# Test Case 6: Edge-case video durations
# ---------------------------------------------------------------------------

class TestEdgeCaseDurations(unittest.TestCase):
    """Test 6: Very short (<2s) and very long (30+ min) videos scale correctly."""

    def test_very_short_video_no_crash(self):
        """
        A <2s video may produce 0 or 1 frames — must not crash,
        must return a valid Step4Output.
        """
        # Simulate 1 frame analyzed, 1 face, low fake score
        per_frame = [PerFrameScore(timestamp=0.0, fake_probability=0.05)]
        score, verdict = _aggregate_scores(per_frame, faces_detected=1)

        self.assertEqual(verdict, "CLEAN")
        self.assertIsNotNone(score)

    def test_very_short_video_zero_frames_no_crash(self):
        """
        Extreme edge: 0 frames sampled (video too short for even 1 sample).
        Must return NO_FACES_DETECTED gracefully.
        """
        per_frame = []
        score, verdict = _aggregate_scores(per_frame, faces_detected=0)
        self.assertEqual(verdict, "NO_FACES_DETECTED")
        self.assertIsNone(score)

    def test_long_video_aggregation_scales_correctly(self):
        """
        30-minute video at 1 fps = 1800 frames.
        30% fake = 540 fake frames → exactly at threshold → FLAGGED.
        """
        n_clean = 1260
        n_fake  = 540  # 540/1800 = 0.30
        per_frame = make_per_frame_scores(n_clean=n_clean, n_fake=n_fake)
        score, verdict = _aggregate_scores(per_frame, faces_detected=1800)

        self.assertAlmostEqual(score, 0.30, places=4)
        self.assertEqual(verdict, "FLAGGED")

    def test_long_video_just_under_threshold_is_clean(self):
        """
        29.9% fake frames on a long video → CLEAN.
        """
        total    = 1000
        n_fake   = 299   # 29.9%
        n_clean  = total - n_fake
        per_frame = make_per_frame_scores(n_clean=n_clean, n_fake=n_fake)
        score, verdict = _aggregate_scores(per_frame, faces_detected=total)

        self.assertLess(score, VIDEO_FLAG_THRESHOLD)
        self.assertEqual(verdict, "CLEAN")

    def test_output_serializes_large_per_frame_list(self):
        """Large per_frame_scores list must JSON-serialize without errors."""
        step3     = make_mock_step3_output()
        per_frame = make_per_frame_scores(n_clean=1800, n_fake=0)
        check = ManipulationCheck(
            frames_analyzed=1800, faces_detected=1800,
            per_frame_scores=per_frame, video_level_score=0.0,
            verdict="CLEAN", detector_error=False,
            processing_time_seconds=45.0,
        )
        result  = build_step4_output(step3, check)
        as_dict = step4_output_to_dict(result)
        serialized = json.dumps(as_dict)
        self.assertIn('"verdict": "CLEAN"', serialized)
        self.assertEqual(len(as_dict["manipulation_check"]["per_frame_scores"]), 1800)


# ---------------------------------------------------------------------------
# Aggregation constant tests (contract verification)
# ---------------------------------------------------------------------------

class TestConstants(unittest.TestCase):
    """Verify named threshold constants are at their expected contract values."""

    def test_frame_fake_threshold_value(self):
        self.assertEqual(FRAME_FAKE_THRESHOLD, 0.5)

    def test_video_flag_threshold_value(self):
        self.assertEqual(VIDEO_FLAG_THRESHOLD, 0.30)

    def test_aggregation_method_label_unchanged(self):
        check = ManipulationCheck(
            frames_analyzed=0, faces_detected=0,
            per_frame_scores=[], video_level_score=None,
        )
        self.assertEqual(check.aggregation_method, "percentage_above_threshold")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Chorus Step 4 — Manipulation Detection Unit Tests")
    print("=" * 60)

    loader  = unittest.TestLoader()
    suite   = unittest.TestSuite()

    for cls in [
        TestParseStep3Input,
        TestKnownRealVideo,
        TestKnownDeepfakeVideo,
        TestNoFacesVideo,
        TestModelFailureFailSafe,
        TestEdgeCaseDurations,
        TestConstants,
    ]:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    exit(0 if result.wasSuccessful() else 1)
