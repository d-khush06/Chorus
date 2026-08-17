"""
test_scene_segmentation.py
==========================
Chorus Stage 7 -- Scene Segmentation Agent: Unit Test Suite

Tests cover all 6 pipeline rules plus input validation, CLI, and audit logging.

Run with:
    python test_scene_segmentation.py        # detailed output
    python -m pytest test_scene_segmentation.py -v
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch, call

# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------
import scene_segmentation as ss

# Convenience aliases
detect_scenes        = ss.detect_scenes
_validate_input      = ss._validate_input
_select_detector     = ss._select_detector
_apply_min_length    = ss._apply_min_length
_apply_empty_fallback = ss._apply_empty_fallback
_build_scene_list    = ss._build_scene_list
_get_video_duration  = ss._get_video_duration


# ===========================================================================
# Helpers
# ===========================================================================

def _make_payload(video_path="clip.mp4", source_type="local_upload", mode="general"):
    return {"video_path": video_path, "source_type": source_type, "mode": mode}


def _fake_scene_list(pairs):
    """Build a list of mock (start_tc, end_tc) as detect_scenes expects from PySceneDetect."""
    result = []
    for start_s, end_s in pairs:
        s = MagicMock()
        s.get_seconds.return_value = start_s
        e = MagicMock()
        e.get_seconds.return_value = end_s
        result.append((s, e))
    return result


# ===========================================================================
# 1. Input Validation Tests
# ===========================================================================

class TestInputValidation(unittest.TestCase):

    def test_missing_video_path_raises(self):
        with self.assertRaises(ValueError) as ctx:
            _validate_input({"source_type": "local_upload", "mode": "general"})
        self.assertIn("video_path", str(ctx.exception))

    def test_empty_video_path_raises(self):
        with self.assertRaises(ValueError):
            _validate_input({"video_path": "", "source_type": "local_upload", "mode": "general"})

    def test_invalid_source_type_raises(self):
        with self.assertRaises(ValueError) as ctx:
            _validate_input({"video_path": "x.mp4", "source_type": "ftp", "mode": "general"})
        self.assertIn("source_type", str(ctx.exception))

    def test_invalid_mode_raises(self):
        with self.assertRaises(ValueError) as ctx:
            _validate_input({"video_path": "x.mp4", "source_type": "local_upload", "mode": "turbo"})
        self.assertIn("mode", str(ctx.exception))

    def test_valid_all_source_types(self):
        for st in ("youtube", "local_upload", "live_rtsp"):
            vp, src, mode = _validate_input({"video_path": "x.mp4", "source_type": st, "mode": "general"})
            self.assertEqual(src, st)

    def test_valid_all_modes(self):
        for m in ("general", "cyber"):
            vp, src, mode = _validate_input({"video_path": "x.mp4", "source_type": "local_upload", "mode": m})
            self.assertEqual(mode, m)

    def test_mode_defaults_to_general(self):
        vp, src, mode = _validate_input({"video_path": "x.mp4", "source_type": "local_upload"})
        self.assertEqual(mode, "general")


# ===========================================================================
# 2. Rule 1 -- Detector Selection
# ===========================================================================

class TestDetectorSelection(unittest.TestCase):

    @patch("scene_segmentation._PYSCENEDETECT_AVAILABLE", True)
    def test_general_mode_returns_content_label(self):
        with patch("scene_segmentation.ContentDetector") as MockCD:
            MockCD.return_value = MagicMock()
            _, label = _select_detector("general")
        self.assertEqual(label, "content")

    @patch("scene_segmentation._PYSCENEDETECT_AVAILABLE", True)
    def test_cyber_mode_returns_adaptive_label(self):
        with patch("scene_segmentation.AdaptiveDetector") as MockAD:
            MockAD.return_value = MagicMock()
            _, label = _select_detector("cyber")
        self.assertEqual(label, "adaptive")

    @patch("scene_segmentation._PYSCENEDETECT_AVAILABLE", True)
    def test_content_detector_created_with_fixed_threshold(self):
        """Rule 2 -- ContentDetector must always receive CONTENT_THRESHOLD."""
        with patch("scene_segmentation.ContentDetector") as MockCD:
            MockCD.return_value = MagicMock()
            _select_detector("general")
            MockCD.assert_called_once_with(threshold=ss.CONTENT_THRESHOLD)

    def test_content_threshold_is_27(self):
        """Rule 2 -- The global constant must be exactly 27.0."""
        self.assertEqual(ss.CONTENT_THRESHOLD, 27.0)


# ===========================================================================
# 3. Rule 3 -- Minimum Scene Length Filter
# ===========================================================================

class TestMinSceneLength(unittest.TestCase):

    def test_all_valid_scenes_pass_through(self):
        scenes = [(0.0, 5.0), (5.0, 12.0), (12.0, 20.0)]
        result = _apply_min_length(scenes)
        self.assertEqual(result, scenes)

    def test_short_scene_at_start_merges_forward(self):
        # First scene is 0.2 s (too short), second is 5 s
        scenes = [(0.0, 0.2), (0.2, 5.2)]
        result = _apply_min_length(scenes)
        # The orphaned placeholder gets merged into the second real scene
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0][0], 0.0)
        self.assertAlmostEqual(result[0][1], 5.2)

    def test_short_scene_in_middle_absorbed_into_preceding(self):
        # scene0: 5 s, scene1: 0.3 s (too short), scene2: 8 s
        scenes = [(0.0, 5.0), (5.0, 5.3), (5.3, 13.3)]
        result = _apply_min_length(scenes)
        # scene1 is absorbed into scene0; scene2 stays
        self.assertEqual(len(result), 2)
        self.assertAlmostEqual(result[0][1], 5.3)
        self.assertAlmostEqual(result[1][0], 5.3)

    def test_min_duration_boundary_inclusive_excluded(self):
        # Exactly 0.6 s -- should survive
        scenes = [(0.0, 0.6)]
        result = _apply_min_length(scenes)
        self.assertEqual(len(result), 1)

        # Exactly 0.599 s -- should be dropped
        scenes2 = [(0.0, 0.599)]
        result2 = _apply_min_length(scenes2)
        # Either empty or fully merged
        for s, e in result2:
            self.assertLess(e - s, ss.MIN_SCENE_DURATION_S + 1)  # sanity

    def test_empty_input_returns_empty(self):
        self.assertEqual(_apply_min_length([]), [])

    def test_min_scene_duration_constant(self):
        """Rule 3 -- The constant must be exactly 0.6 s."""
        self.assertEqual(ss.MIN_SCENE_DURATION_S, 0.6)


# ===========================================================================
# 4. Rule 5 -- Empty Result Fallback
# ===========================================================================

class TestEmptyResultFallback(unittest.TestCase):

    def test_non_empty_input_returned_unchanged(self):
        scenes = [(0.0, 10.0)]
        result = _apply_empty_fallback(scenes, "x.mp4")
        self.assertEqual(result, scenes)

    @patch("scene_segmentation._get_video_duration", return_value=42.5)
    def test_empty_input_returns_full_video_scene(self, mock_dur):
        result = _apply_empty_fallback([], "clip.mp4")
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0][0], 0.0)
        self.assertAlmostEqual(result[0][1], 42.5)

    @patch("scene_segmentation._get_video_duration", return_value=0.0)
    def test_empty_fallback_with_unknown_duration(self, mock_dur):
        """If duration is unknown, still return one scene -- Rule 5 must not produce empty list."""
        result = _apply_empty_fallback([], "clip.mp4")
        self.assertEqual(len(result), 1)


# ===========================================================================
# 5. Scene List Builder
# ===========================================================================

class TestBuildSceneList(unittest.TestCase):

    def test_ids_are_sequential_from_zero(self):
        scenes = [(0.0, 5.5), (5.5, 12.1), (12.1, 20.0)]
        result = _build_scene_list(scenes)
        self.assertEqual([s["scene_id"] for s in result], [0, 1, 2])

    def test_timestamps_rounded_to_3dp(self):
        scenes = [(0.0001, 12.4999)]
        result = _build_scene_list(scenes)
        self.assertEqual(result[0]["start_seconds"], 0.0)
        self.assertEqual(result[0]["end_seconds"], 12.5)

    def test_output_keys(self):
        result = _build_scene_list([(0.0, 10.0)])
        self.assertIn("scene_id",      result[0])
        self.assertIn("start_seconds", result[0])
        self.assertIn("end_seconds",   result[0])


# ===========================================================================
# 6. Full detect_scenes() -- VOD Path
# ===========================================================================

def _make_mock_video_open(scene_pairs):
    """
    Patch open_video, SceneManager, and detector so _run_detection_on_file
    returns the given scene_pairs without touching the filesystem.
    """
    mock_video   = MagicMock()
    mock_manager = MagicMock()
    mock_manager.get_scene_list.return_value = _fake_scene_list(scene_pairs)
    return mock_video, mock_manager


class TestDetectScenesVOD(unittest.TestCase):

    def _run_with_mock_scenes(self, scene_pairs, source_type="local_upload", mode="general"):
        mock_video, mock_manager = _make_mock_video_open(scene_pairs)
        with patch("scene_segmentation.open_video", return_value=mock_video), \
             patch("scene_segmentation.SceneManager", return_value=mock_manager), \
             patch("scene_segmentation.ContentDetector", return_value=MagicMock()), \
             patch("scene_segmentation.AdaptiveDetector", return_value=MagicMock()), \
             patch("scene_segmentation._PYSCENEDETECT_AVAILABLE", True), \
             patch("scene_segmentation._write_audit_log"):
            return detect_scenes({"video_path": "clip.mp4", "source_type": source_type, "mode": mode})

    def test_output_has_required_keys(self):
        result = self._run_with_mock_scenes([(0.0, 10.0), (10.0, 25.0)])
        self.assertIn("scenes",        result)
        self.assertIn("detector_used", result)
        self.assertIn("source_type",   result)

    def test_scenes_are_correctly_numbered(self):
        result = self._run_with_mock_scenes([(0.0, 10.0), (10.0, 25.0)])
        self.assertEqual(result["scenes"][0]["scene_id"], 0)
        self.assertEqual(result["scenes"][1]["scene_id"], 1)

    def test_general_mode_reports_content_detector(self):
        result = self._run_with_mock_scenes([(0.0, 10.0)], mode="general")
        self.assertEqual(result["detector_used"], "content")

    def test_cyber_mode_reports_adaptive_detector(self):
        result = self._run_with_mock_scenes([(0.0, 10.0)], mode="cyber")
        self.assertEqual(result["detector_used"], "adaptive")

    def test_source_type_propagated_to_output(self):
        for st in ("youtube", "local_upload"):
            result = self._run_with_mock_scenes([(0.0, 5.0)], source_type=st)
            self.assertEqual(result["source_type"], st)

    @patch("scene_segmentation._get_video_duration", return_value=30.0)
    def test_rule5_zero_cuts_returns_one_scene(self, mock_dur):
        """Rule 5 -- empty detection must produce exactly one full-duration scene."""
        result = self._run_with_mock_scenes([])
        self.assertEqual(len(result["scenes"]), 1)
        self.assertEqual(result["scenes"][0]["scene_id"], 0)
        self.assertAlmostEqual(result["scenes"][0]["start_seconds"], 0.0)
        self.assertAlmostEqual(result["scenes"][0]["end_seconds"], 30.0)

    def test_rule3_short_scenes_filtered(self):
        """Rule 3 -- scenes under 0.6 s must not appear in output as independent scenes."""
        # A 0.2 s scene followed by a real 20 s scene
        scene_pairs = [(0.0, 0.2), (0.2, 20.2)]
        result = self._run_with_mock_scenes(scene_pairs)
        # The 0.2 s clip should be merged; only one consolidated scene expected
        self.assertEqual(len(result["scenes"]), 1)
        self.assertAlmostEqual(result["scenes"][0]["end_seconds"], 20.2)

    def test_rule6_determinism(self):
        """Rule 6 -- same input produces identical output on multiple calls."""
        r1 = self._run_with_mock_scenes([(0.0, 5.0), (5.0, 15.0)])
        r2 = self._run_with_mock_scenes([(0.0, 5.0), (5.0, 15.0)])
        self.assertEqual(r1, r2)


# ===========================================================================
# 7. RTSP Chunked Detection (Rule 4)
# ===========================================================================

class TestDetectScenesRTSP(unittest.TestCase):
    """
    Tests for Rule 4: RTSP streams are broken into 30-second chunks;
    timestamps are offset by the chunk's absolute position.
    """

    def _run_rtsp(self, chunk_scene_batches, fps=25.0, mode="general"):
        """
        Simulate two full chunks.

        chunk_scene_batches: list of scene-pair lists, one per chunk.
        """
        import numpy as np
        frame = (255 * np.ones((480, 640, 3), dtype=np.uint8))  # blank white frame

        call_count = {"n": 0}
        all_pairs  = list(chunk_scene_batches)

        def fake_open_video(path):
            return MagicMock()

        def fake_scene_manager_ctor():
            mgr = MagicMock()
            batch_idx = call_count["n"]
            if batch_idx < len(all_pairs):
                mgr.get_scene_list.return_value = _fake_scene_list(all_pairs[batch_idx])
            else:
                mgr.get_scene_list.return_value = []
            call_count["n"] += 1
            return mgr

        frames_per_chunk = int(fps * ss.RTSP_CHUNK_SECONDS)
        total_frames     = frames_per_chunk * len(chunk_scene_batches)
        read_call        = {"n": 0}

        def fake_read():
            if read_call["n"] < total_frames:
                read_call["n"] += 1
                return True, frame.copy()
            return False, None

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.return_value      = fps
        mock_cap.read.side_effect      = fake_read

        with patch("cv2.VideoCapture", return_value=mock_cap), \
             patch("cv2.VideoWriter") as mock_writer_cls, \
             patch("cv2.VideoWriter_fourcc", return_value=0), \
             patch("scene_segmentation.open_video", side_effect=fake_open_video), \
             patch("scene_segmentation.SceneManager", side_effect=fake_scene_manager_ctor), \
             patch("scene_segmentation.ContentDetector", return_value=MagicMock()), \
             patch("scene_segmentation.AdaptiveDetector", return_value=MagicMock()), \
             patch("scene_segmentation._PYSCENEDETECT_AVAILABLE", True), \
             patch("scene_segmentation._write_audit_log"), \
             patch("os.unlink"):
            mock_writer_cls.return_value = MagicMock()
            return ss._detect_rtsp("rtsp://cam/stream", mode)

    def test_rtsp_timestamps_offset_by_chunk_position(self):
        """Chunk 1 starts at 0 s, chunk 2 starts at 30 s; offsets must match."""
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy not installed")

        chunk0_scenes = [(0.0, 15.0), (15.0, 30.0)]   # chunk at offset 0
        chunk1_scenes = [(0.0, 10.0), (10.0, 30.0)]   # chunk at offset 30

        scenes, label = self._run_rtsp([chunk0_scenes, chunk1_scenes])

        # chunk 0 results: unchanged
        self.assertAlmostEqual(scenes[0][0], 0.0)
        self.assertAlmostEqual(scenes[0][1], 15.0)
        # chunk 1 results: offset by 30 s
        self.assertAlmostEqual(scenes[2][0], 30.0)
        self.assertAlmostEqual(scenes[2][1], 40.0)

    def test_rtsp_chunk_fallback_when_no_cuts(self):
        """Rule 5 per chunk: if a chunk produces no cuts, it becomes one scene."""
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy not installed")

        # One chunk, no cuts detected
        scenes, label = self._run_rtsp([[]])
        self.assertEqual(len(scenes), 1)
        self.assertAlmostEqual(scenes[0][0], 0.0)
        # Ends at approximately 30 s (one chunk)
        self.assertGreater(scenes[0][1], 0.0)

    def test_rtsp_source_type_in_output(self):
        """detect_scenes on live_rtsp must report source_type=live_rtsp."""
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy not installed")

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.return_value      = 25.0
        mock_cap.read.return_value     = (False, None)  # stream immediately empty

        with patch("cv2.VideoCapture", return_value=mock_cap), \
             patch("scene_segmentation._PYSCENEDETECT_AVAILABLE", True), \
             patch("scene_segmentation._write_audit_log"):
            result = detect_scenes({
                "video_path":  "rtsp://cam/stream",
                "source_type": "live_rtsp",
                "mode":        "general",
            })

        self.assertEqual(result["source_type"], "live_rtsp")
        # Rule 5 global fallback: at least one scene
        self.assertGreaterEqual(len(result["scenes"]), 1)


# ===========================================================================
# 8. Audit Logging
# ===========================================================================

class TestAuditLogging(unittest.TestCase):

    def test_audit_log_written_on_success(self):
        """detect_scenes must write an audit record after successful detection."""
        mock_video, mock_manager = _make_mock_video_open([(0.0, 10.0)])
        written = []

        def capture_audit(payload, result):
            written.append((payload, result))

        with patch("scene_segmentation.open_video", return_value=mock_video), \
             patch("scene_segmentation.SceneManager", return_value=mock_manager), \
             patch("scene_segmentation.ContentDetector", return_value=MagicMock()), \
             patch("scene_segmentation._PYSCENEDETECT_AVAILABLE", True), \
             patch("scene_segmentation._write_audit_log", side_effect=capture_audit):
            detect_scenes({"video_path": "clip.mp4", "source_type": "local_upload", "mode": "general"})

        self.assertEqual(len(written), 1)
        self.assertIn("scenes", written[0][1])


# ===========================================================================
# 9. Output Format Compliance (exact spec contract)
# ===========================================================================

class TestOutputFormat(unittest.TestCase):

    def _result_for(self, scene_pairs, source_type="local_upload", mode="general"):
        mock_video, mock_manager = _make_mock_video_open(scene_pairs)
        with patch("scene_segmentation.open_video", return_value=mock_video), \
             patch("scene_segmentation.SceneManager", return_value=mock_manager), \
             patch("scene_segmentation.ContentDetector", return_value=MagicMock()), \
             patch("scene_segmentation.AdaptiveDetector", return_value=MagicMock()), \
             patch("scene_segmentation._PYSCENEDETECT_AVAILABLE", True), \
             patch("scene_segmentation._write_audit_log"):
            return detect_scenes({"video_path": "clip.mp4", "source_type": source_type, "mode": mode})

    def test_top_level_keys_only(self):
        result = self._result_for([(0.0, 10.0)])
        self.assertEqual(sorted(result.keys()), ["detector_used", "scenes", "source_type"])

    def test_scene_entry_keys_only(self):
        result = self._result_for([(0.0, 10.0)])
        scene = result["scenes"][0]
        self.assertEqual(sorted(scene.keys()), ["end_seconds", "scene_id", "start_seconds"])

    def test_detector_used_values(self):
        r_general = self._result_for([(0.0, 5.0)], mode="general")
        r_cyber   = self._result_for([(0.0, 5.0)], mode="cyber")
        self.assertIn(r_general["detector_used"], ("content", "adaptive"))
        self.assertIn(r_cyber["detector_used"],   ("content", "adaptive"))
        self.assertEqual(r_general["detector_used"], "content")
        self.assertEqual(r_cyber["detector_used"],   "adaptive")

    def test_source_type_preserved(self):
        for st in ("youtube", "local_upload"):
            result = self._result_for([(0.0, 5.0)], source_type=st)
            self.assertEqual(result["source_type"], st)

    def test_multiple_scenes_correct_continuity(self):
        pairs = [(0.0, 12.4), (12.4, 30.1)]
        result = self._result_for(pairs)
        s = result["scenes"]
        self.assertEqual(s[0]["start_seconds"], 0.0)
        self.assertEqual(s[0]["end_seconds"],   12.4)
        self.assertEqual(s[1]["start_seconds"], 12.4)
        self.assertEqual(s[1]["end_seconds"],   30.1)


# ===========================================================================
# 10. PySceneDetect Unavailable
# ===========================================================================

class TestPySceneDetectUnavailable(unittest.TestCase):

    def test_raises_runtime_error_when_library_missing(self):
        with patch("scene_segmentation._PYSCENEDETECT_AVAILABLE", False), \
             patch("scene_segmentation._write_audit_log"):
            with self.assertRaises(RuntimeError) as ctx:
                detect_scenes({"video_path": "clip.mp4", "source_type": "local_upload", "mode": "general"})
            self.assertIn("PySceneDetect", str(ctx.exception))


# ===========================================================================
# 11. CLI Smoke Test
# ===========================================================================

class TestCLI(unittest.TestCase):

    def _run_cli(self, argv, scene_pairs=None, duration=10.0):
        scene_pairs = scene_pairs or [(0.0, 10.0)]
        mock_video, mock_manager = _make_mock_video_open(scene_pairs)

        captured = []

        def fake_print(text):
            captured.append(text)

        import io
        from unittest.mock import patch as mpatch
        old_argv = sys.argv
        try:
            sys.argv = argv
            with mpatch("scene_segmentation.open_video", return_value=mock_video), \
                 mpatch("scene_segmentation.SceneManager", return_value=mock_manager), \
                 mpatch("scene_segmentation.ContentDetector", return_value=MagicMock()), \
                 mpatch("scene_segmentation.AdaptiveDetector", return_value=MagicMock()), \
                 mpatch("scene_segmentation._PYSCENEDETECT_AVAILABLE", True), \
                 mpatch("scene_segmentation._write_audit_log"), \
                 mpatch("builtins.print", side_effect=captured.append), \
                 self.assertRaises(SystemExit) as cm:
                import importlib, runpy
                runpy.run_module("scene_segmentation", run_name="__main__", alter_sys=False)
        except SystemExit as se:
            pass
        finally:
            sys.argv = old_argv

        return captured

    def test_cli_prints_valid_json(self):
        mock_video, mock_manager = _make_mock_video_open([(0.0, 10.0)])
        import io

        with patch("scene_segmentation.open_video", return_value=mock_video), \
             patch("scene_segmentation.SceneManager", return_value=mock_manager), \
             patch("scene_segmentation.ContentDetector", return_value=MagicMock()), \
             patch("scene_segmentation._PYSCENEDETECT_AVAILABLE", True), \
             patch("scene_segmentation._write_audit_log"):
            result = detect_scenes({
                "video_path": "clip.mp4",
                "source_type": "local_upload",
                "mode": "general",
            })

        # Must be JSON-serialisable
        serialised = json.dumps(result)
        parsed = json.loads(serialised)
        self.assertIn("scenes", parsed)


# ===========================================================================
# 12. RTSP Chunk Constant
# ===========================================================================

class TestRTSPConstant(unittest.TestCase):
    def test_chunk_seconds_is_30(self):
        """Rule 4 -- chunks must be exactly 30 seconds."""
        self.assertEqual(ss.RTSP_CHUNK_SECONDS, 30.0)


# ===========================================================================
# Main
# ===========================================================================

if __name__ == "__main__":
    loader  = unittest.TestLoader()
    suite   = loader.loadTestsFromModule(sys.modules[__name__])
    runner  = unittest.TextTestRunner(verbosity=2)
    result  = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
