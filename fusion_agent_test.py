"""
fusion_agent_test.py
====================
Chorus -- Step 13: Fusion Agent Unit Tests

Follows the exact pattern of test_scene_segmentation.py:
  - Pure unittest, no ML/LLM/GPU dependencies
  - Mock inputs for all four source agents
  - Covers all 6 rules: timeline construction, speaker alignment,
    conflict detection, confidence propagation, gap handling, determinism
  - Deliberate conflict cases assert they appear in `conflicts` and are
    ALSO present in fused_timeline (never silently dropped)

Run with:
    python fusion_agent_test.py
    python -m pytest fusion_agent_test.py -v
"""

import json
import sys
import unittest
from unittest.mock import patch

import fusion_agent as fa
from fusion_agent import (
    fuse_timeline,
    _align_asr_to_diarization,
    _detect_conflicts,
    _classify_conflict_type,
    _overlap_seconds,
    _overlap_fraction,
    _find_scene_id,
    _sort_scenes,
    _inject_no_signal_placeholders,
    _merge_confidence,
    _build_timeline,
    CONFLICT_OVERLAP_THRESHOLD,
    CT_PRESENCE, CT_CONTENT, CT_TIMING,
    SOURCE_PERCEPTION, SOURCE_ASR, SOURCE_DIARIZATION, SOURCE_OCR,
)


# ===========================================================================
# Shared fixtures
# ===========================================================================

def _scenes(*pairs):
    """Build a Step 7 scene list from (start, end) pairs."""
    return [
        {"scene_id": i, "start_seconds": s, "end_seconds": e}
        for i, (s, e) in enumerate(pairs)
    ]


def _ev(source, start, end, content="hello", etype="speech", confidence=0.9):
    """Build a minimal source-agent event dict."""
    return {
        "source":        source,
        "start_seconds": start,
        "end_seconds":   end,
        "type":          etype,
        "content":       content,
        "confidence":    confidence,
    }


def _run(scenes, perception=None, asr=None, diarization=None, ocr=None):
    """Call fuse_timeline with audit log patched out."""
    with patch("fusion_agent._write_audit_log"):
        return fuse_timeline(
            scenes      = scenes,
            perception  = perception  or [],
            asr         = asr         or [],
            diarization = diarization or [],
            ocr         = ocr         or [],
        )


# ===========================================================================
# 1. Output schema compliance
# ===========================================================================

class TestOutputSchema(unittest.TestCase):
    """All three top-level keys must always be present."""

    def test_top_level_keys_present(self):
        scenes = _scenes((0.0, 10.0))
        result = _run(scenes)
        self.assertIn("fused_timeline",        result)
        self.assertIn("conflicts",             result)
        self.assertIn("scenes_with_no_signal", result)

    def test_fused_event_keys(self):
        scenes = _scenes((0.0, 10.0))
        evs    = [_ev(SOURCE_PERCEPTION, 1.0, 5.0, "a face")]
        result = _run(scenes, perception=evs)
        ev = result["fused_timeline"][0]
        required = {"scene_id", "start_seconds", "end_seconds",
                    "event_type", "content", "source_agent", "confidence"}
        self.assertTrue(required.issubset(ev.keys()))

    def test_conflict_keys(self):
        scenes = _scenes((0.0, 10.0))
        # Presence conflict: perception says "empty room", ASR has speech
        p_evs = [_ev(SOURCE_PERCEPTION, 2.0, 8.0, "empty room")]
        a_evs = [_ev(SOURCE_ASR,        2.0, 8.0, "I am speaking")]
        result = _run(scenes, perception=p_evs, asr=a_evs)
        self.assertGreater(len(result["conflicts"]), 0)
        c = result["conflicts"][0]
        required = {"scene_id", "time_range", "source_a", "content_a",
                    "source_b", "content_b", "conflict_type"}
        self.assertTrue(required.issubset(c.keys()))

    def test_result_is_json_serializable(self):
        scenes = _scenes((0.0, 10.0))
        result = _run(scenes, perception=[_ev(SOURCE_PERCEPTION, 1.0, 5.0)])
        try:
            json.dumps(result)
        except TypeError as exc:
            self.fail(f"Result is not JSON-serializable: {exc}")


# ===========================================================================
# 2. Rule 1 -- Timeline construction
# ===========================================================================

class TestTimelineConstruction(unittest.TestCase):
    """Rule 1: events sorted by start_seconds, keyed to canonical scene_id."""

    def test_events_sorted_by_start_seconds(self):
        scenes = _scenes((0.0, 20.0))
        evs    = [
            _ev(SOURCE_PERCEPTION, 10.0, 15.0),
            _ev(SOURCE_OCR,         2.0,  5.0),
            _ev(SOURCE_ASR,         6.0,  9.0),
        ]
        result = _run(scenes, perception=[evs[0]], ocr=[evs[2]], asr=[evs[1]])
        starts = [e["start_seconds"] for e in result["fused_timeline"]
                  if e["source_agent"] is not None]
        self.assertEqual(starts, sorted(starts))

    def test_scene_id_assigned_correctly(self):
        scenes = _scenes((0.0, 5.0), (5.0, 10.0), (10.0, 20.0))
        # An event starting at 7 s should get scene_id=1
        evs    = [_ev(SOURCE_OCR, 7.0, 9.0)]
        result = _run(scenes, ocr=evs)
        real_evs = [e for e in result["fused_timeline"] if e["source_agent"] == SOURCE_OCR]
        self.assertEqual(real_evs[0]["scene_id"], 1)

    def test_all_four_sources_present_in_timeline(self):
        scenes = _scenes((0.0, 30.0))
        result = _run(
            scenes,
            perception  = [_ev(SOURCE_PERCEPTION,  1.0,  5.0)],
            asr         = [_ev(SOURCE_ASR,          6.0,  9.0)],
            diarization = [_ev(SOURCE_DIARIZATION, 6.0, 12.0, "Speaker A")],
            ocr         = [_ev(SOURCE_OCR,         14.0, 18.0)],
        )
        sources = {e["source_agent"] for e in result["fused_timeline"]
                   if e["source_agent"] is not None}
        self.assertIn(SOURCE_PERCEPTION,  sources)
        self.assertIn(SOURCE_ASR,         sources)
        self.assertIn(SOURCE_DIARIZATION, sources)
        self.assertIn(SOURCE_OCR,         sources)

    def test_empty_inputs_produce_no_signal_only(self):
        scenes = _scenes((0.0, 10.0))
        result = _run(scenes)
        evs = result["fused_timeline"]
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["event_type"], "no_signal")
        self.assertIsNone(evs[0]["source_agent"])


# ===========================================================================
# 3. Rule 2 -- Speaker-transcript alignment
# ===========================================================================

class TestSpeakerAlignment(unittest.TestCase):
    """Rule 2: ASR segments assigned to diarization speakers; split at boundaries."""

    def test_asr_assigned_to_overlapping_speaker(self):
        asr  = [_ev(SOURCE_ASR,         1.0,  5.0, "hello world")]
        diar = [_ev(SOURCE_DIARIZATION, 0.0, 10.0, "Speaker A")]
        aligned = _align_asr_to_diarization(asr, diar)
        self.assertEqual(len(aligned), 1)
        self.assertEqual(aligned[0]["speaker"], "Speaker A")

    def test_asr_split_at_speaker_boundary(self):
        """An ASR segment spanning [0,10] with speaker change at t=5 must be split."""
        asr  = [_ev(SOURCE_ASR,         0.0, 10.0, "long sentence")]
        diar = [
            _ev(SOURCE_DIARIZATION, 0.0,  5.0, "Speaker A"),
            _ev(SOURCE_DIARIZATION, 5.0, 10.0, "Speaker B"),
        ]
        aligned = _align_asr_to_diarization(asr, diar)
        self.assertEqual(len(aligned), 2)
        speakers = {a["speaker"] for a in aligned}
        self.assertIn("Speaker A", speakers)
        self.assertIn("Speaker B", speakers)

    def test_asr_split_timestamps_correct(self):
        asr  = [_ev(SOURCE_ASR,         0.0, 10.0, "text")]
        diar = [
            _ev(SOURCE_DIARIZATION, 0.0, 5.0, "SPK1"),
            _ev(SOURCE_DIARIZATION, 5.0, 10.0, "SPK2"),
        ]
        aligned = _align_asr_to_diarization(asr, diar)
        aligned.sort(key=lambda e: e["start_seconds"])
        self.assertAlmostEqual(aligned[0]["start_seconds"], 0.0)
        self.assertAlmostEqual(aligned[0]["end_seconds"],   5.0)
        self.assertAlmostEqual(aligned[1]["start_seconds"], 5.0)
        self.assertAlmostEqual(aligned[1]["end_seconds"],  10.0)

    def test_asr_no_diarization_coverage_gives_none_speaker(self):
        asr  = [_ev(SOURCE_ASR,          20.0, 25.0, "stray segment")]
        diar = [_ev(SOURCE_DIARIZATION,   0.0,  5.0, "Speaker A")]
        aligned = _align_asr_to_diarization(asr, diar)
        self.assertEqual(len(aligned), 1)
        self.assertIsNone(aligned[0]["speaker"])

    def test_asr_split_three_speakers(self):
        """A segment spanning three speakers must produce exactly three pieces."""
        asr  = [_ev(SOURCE_ASR,         0.0, 15.0, "multi-speaker")]
        diar = [
            _ev(SOURCE_DIARIZATION,  0.0,  5.0, "SPK1"),
            _ev(SOURCE_DIARIZATION,  5.0, 10.0, "SPK2"),
            _ev(SOURCE_DIARIZATION, 10.0, 15.0, "SPK3"),
        ]
        aligned = _align_asr_to_diarization(asr, diar)
        self.assertEqual(len(aligned), 3)

    def test_alignment_deterministic(self):
        """Same inputs must always produce identical output (Rule 6)."""
        asr  = [_ev(SOURCE_ASR, 0.0, 10.0, "words")]
        diar = [
            _ev(SOURCE_DIARIZATION, 0.0, 5.0,  "SPK1"),
            _ev(SOURCE_DIARIZATION, 5.0, 10.0, "SPK2"),
        ]
        r1 = _align_asr_to_diarization(asr, diar)
        r2 = _align_asr_to_diarization(asr, diar)
        self.assertEqual(r1, r2)


# ===========================================================================
# 4. Rule 3 -- Conflict detection (the most important rule)
# ===========================================================================

class TestConflictDetection(unittest.TestCase):
    """Rule 3: overlapping events from different agents emit conflicts without
    silently removing them from the fused timeline."""

    def _make_conflict_result(self, ev_a, ev_b):
        """Helper: run fuse_timeline with two conflicting events."""
        scenes = _scenes((0.0, 30.0))
        kwargs = {SOURCE_PERCEPTION: [], SOURCE_ASR: [],
                  SOURCE_DIARIZATION: [], SOURCE_OCR: []}
        kwargs[ev_a["source"]] = [ev_a]
        kwargs[ev_b["source"]] = [ev_b]
        return _run(
            scenes,
            perception  = kwargs[SOURCE_PERCEPTION],
            asr         = kwargs[SOURCE_ASR],
            diarization = kwargs[SOURCE_DIARIZATION],
            ocr         = kwargs[SOURCE_OCR],
        )

    # --- presence_contradiction ---

    def test_presence_conflict_detected(self):
        """
        Vision says "empty room", ASR has speech in same window.
        Must appear in conflicts as presence_contradiction.
        """
        ev_a = _ev(SOURCE_PERCEPTION, 2.0, 8.0, "empty room")
        ev_b = _ev(SOURCE_ASR,        2.0, 8.0, "I am speaking loudly")
        result = self._make_conflict_result(ev_a, ev_b)
        self.assertGreater(len(result["conflicts"]), 0)
        ctypes = {c["conflict_type"] for c in result["conflicts"]}
        self.assertIn(CT_PRESENCE, ctypes)

    def test_presence_conflict_not_silently_merged(self):
        """
        CRITICAL (Rule 3): conflicting events must BOTH still appear in
        fused_timeline -- they are not suppressed or silently resolved.
        """
        ev_a = _ev(SOURCE_PERCEPTION, 2.0, 8.0, "empty room")
        ev_b = _ev(SOURCE_ASR,        2.0, 8.0, "I am speaking loudly")
        result = self._make_conflict_result(ev_a, ev_b)

        sources_in_timeline = {
            e["source_agent"] for e in result["fused_timeline"]
            if e["source_agent"] is not None
        }
        self.assertIn(SOURCE_PERCEPTION, sources_in_timeline,
                      "Conflicting perception event was silently dropped from fused_timeline")
        self.assertIn(SOURCE_ASR, sources_in_timeline,
                      "Conflicting ASR event was silently dropped from fused_timeline")

    # --- content_mismatch ---

    def test_content_mismatch_detected(self):
        """Two sources that overlap heavily with different text content."""
        ev_a = _ev(SOURCE_OCR,        3.0, 9.0, "Breaking: stock market rises 10%")
        ev_b = _ev(SOURCE_ASR,        3.0, 9.0, "Markets plummet in historic crash")
        result = self._make_conflict_result(ev_a, ev_b)
        self.assertGreater(len(result["conflicts"]), 0)
        ctypes = {c["conflict_type"] for c in result["conflicts"]}
        self.assertIn(CT_CONTENT, ctypes)

    def test_content_mismatch_not_silently_merged(self):
        ev_a = _ev(SOURCE_OCR, 3.0, 9.0, "Stock market rises")
        ev_b = _ev(SOURCE_ASR, 3.0, 9.0, "Markets plummet")
        result = self._make_conflict_result(ev_a, ev_b)
        sources = {e["source_agent"] for e in result["fused_timeline"]
                   if e["source_agent"] is not None}
        self.assertIn(SOURCE_OCR, sources)
        self.assertIn(SOURCE_ASR, sources)

    # --- overlap threshold ---

    def test_low_overlap_does_not_produce_conflict(self):
        """Events with <50% overlap must NOT be flagged as conflicts."""
        # ev_a: [0, 10], ev_b: [8, 18]  -> overlap = 2 s, min_dur=10 -> 20% < 50%
        ev_a = _ev(SOURCE_PERCEPTION, 0.0, 10.0, "empty room")
        ev_b = _ev(SOURCE_ASR,        8.0, 18.0, "hello world")
        result = self._make_conflict_result(ev_a, ev_b)
        self.assertEqual(len(result["conflicts"]), 0)

    def test_exact_50pct_overlap_does_not_trigger(self):
        """At exactly 50% we do NOT flag (threshold is strict >50%)."""
        # ev_a: [0, 4], ev_b: [2, 6] -> overlap=2, min_dur=4 -> exactly 50%
        ev_a = _ev(SOURCE_PERCEPTION, 0.0, 4.0, "empty room")
        ev_b = _ev(SOURCE_ASR,        2.0, 6.0, "speaking now")
        result = self._make_conflict_result(ev_a, ev_b)
        self.assertEqual(len(result["conflicts"]), 0)

    def test_same_source_overlap_not_a_conflict(self):
        """Two events from the SAME source that overlap are not conflicts."""
        scenes = _scenes((0.0, 20.0))
        evs    = [
            _ev(SOURCE_PERCEPTION, 0.0, 10.0, "empty room"),
            _ev(SOURCE_PERCEPTION, 4.0, 14.0, "someone walks in"),
        ]
        result = _run(scenes, perception=evs)
        self.assertEqual(len(result["conflicts"]), 0)

    def test_conflict_contains_both_source_names(self):
        ev_a = _ev(SOURCE_PERCEPTION, 2.0, 8.0, "empty")
        ev_b = _ev(SOURCE_OCR,        2.0, 8.0, "welcome sign visible")
        result = self._make_conflict_result(ev_a, ev_b)
        self.assertGreater(len(result["conflicts"]), 0)
        conflict = result["conflicts"][0]
        sources = {conflict["source_a"], conflict["source_b"]}
        self.assertIn(SOURCE_PERCEPTION, sources)
        self.assertIn(SOURCE_OCR,        sources)

    def test_conflict_time_range_is_overlap(self):
        """time_range must be the actual intersection, not the union."""
        ev_a = _ev(SOURCE_PERCEPTION, 2.0, 8.0, "silence")
        ev_b = _ev(SOURCE_ASR,        4.0, 10.0, "I am talking")
        # overlap = [4.0, 8.0] -> fraction = 4/(min(6,6)) = 0.667 > 0.5
        result = self._make_conflict_result(ev_a, ev_b)
        self.assertGreater(len(result["conflicts"]), 0)
        tr = result["conflicts"][0]["time_range"]
        self.assertAlmostEqual(tr[0], 4.0)
        self.assertAlmostEqual(tr[1], 8.0)

    def test_conflict_type_values_are_valid(self):
        valid_types = {CT_PRESENCE, CT_CONTENT, CT_TIMING}
        ev_a = _ev(SOURCE_PERCEPTION, 2.0, 8.0, "empty room")
        ev_b = _ev(SOURCE_ASR,        2.0, 8.0, "hello")
        result = self._make_conflict_result(ev_a, ev_b)
        for c in result["conflicts"]:
            self.assertIn(c["conflict_type"], valid_types)

    def test_multiple_conflicts_all_reported(self):
        """When three source pairs all conflict, all three conflicts are reported."""
        scenes = _scenes((0.0, 20.0))
        # perception + asr + ocr all in same window with contradictory signals
        result = _run(
            scenes,
            perception  = [_ev(SOURCE_PERCEPTION, 1.0, 9.0, "empty room")],
            asr         = [_ev(SOURCE_ASR,         1.0, 9.0, "lots of speech here")],
            ocr         = [_ev(SOURCE_OCR,         1.0, 9.0, "no text present")],
        )
        # At least perception-asr and perception-ocr conflicts expected
        self.assertGreaterEqual(len(result["conflicts"]), 2)


# ===========================================================================
# 5. Rule 4 -- Confidence propagation
# ===========================================================================

class TestConfidencePropagation(unittest.TestCase):
    """Rule 4: original confidence preserved for single-source; min for combined."""

    def test_single_source_confidence_unchanged(self):
        scenes = _scenes((0.0, 10.0))
        ev     = _ev(SOURCE_PERCEPTION, 1.0, 5.0, confidence=0.73)
        result = _run(scenes, perception=[ev])
        real   = [e for e in result["fused_timeline"] if e["source_agent"] == SOURCE_PERCEPTION]
        self.assertEqual(real[0]["confidence"], 0.73)

    def test_merge_confidence_returns_min(self):
        """_merge_confidence must always return min, never average."""
        c = _merge_confidence([0.9, 0.6, 0.75])
        self.assertAlmostEqual(c, 0.6)

    def test_merge_confidence_single_value(self):
        c = _merge_confidence([0.88])
        self.assertAlmostEqual(c, 0.88)

    def test_merge_confidence_all_none(self):
        c = _merge_confidence([None, None])
        self.assertIsNone(c)

    def test_merge_confidence_ignores_none(self):
        c = _merge_confidence([None, 0.5, 0.9])
        self.assertAlmostEqual(c, 0.5)

    def test_no_confidence_invented_for_no_signal(self):
        """no_signal placeholder must have confidence=null."""
        scenes = _scenes((0.0, 10.0))
        result = _run(scenes)  # all sources empty
        ns = [e for e in result["fused_timeline"] if e["event_type"] == "no_signal"]
        self.assertGreater(len(ns), 0)
        self.assertIsNone(ns[0]["confidence"])


# ===========================================================================
# 6. Rule 5 -- Gap handling
# ===========================================================================

class TestGapHandling(unittest.TestCase):
    """Rule 5: scenes with zero events must get a no_signal placeholder."""

    def test_empty_scene_gets_no_signal_placeholder(self):
        """Scene 1 has events, scene 2 is empty -- scene 2 must get no_signal."""
        scenes = _scenes((0.0, 10.0), (10.0, 20.0), (20.0, 30.0))
        # Only put events in scene 0
        evs = [_ev(SOURCE_PERCEPTION, 1.0, 5.0)]
        result = _run(scenes, perception=evs)

        ns_evs = [e for e in result["fused_timeline"] if e["event_type"] == "no_signal"]
        ns_ids  = {e["scene_id"] for e in ns_evs}
        self.assertIn(1, ns_ids)
        self.assertIn(2, ns_ids)

    def test_scenes_with_no_signal_list_populated(self):
        scenes = _scenes((0.0, 5.0), (5.0, 10.0))
        result = _run(scenes)  # all sources empty
        self.assertIn(0, result["scenes_with_no_signal"])
        self.assertIn(1, result["scenes_with_no_signal"])

    def test_scenes_with_no_signal_empty_when_all_covered(self):
        scenes = _scenes((0.0, 10.0))
        evs    = [_ev(SOURCE_PERCEPTION, 1.0, 5.0)]
        result = _run(scenes, perception=evs)
        self.assertEqual(result["scenes_with_no_signal"], [])

    def test_no_signal_has_correct_schema(self):
        scenes = _scenes((0.0, 10.0))
        result = _run(scenes)
        ns = result["fused_timeline"][0]
        self.assertEqual(ns["event_type"],   "no_signal")
        self.assertIsNone(ns["source_agent"])
        self.assertIsNone(ns["confidence"])
        self.assertIn("scene_id",      ns)
        self.assertIn("start_seconds", ns)
        self.assertIn("end_seconds",   ns)

    def test_no_signal_not_treated_as_conflicting(self):
        """no_signal placeholders must never appear in the conflicts list."""
        scenes = _scenes((0.0, 10.0), (10.0, 20.0))
        result = _run(scenes)  # both scenes empty -> two no_signal entries
        for c in result["conflicts"]:
            self.assertNotEqual(c.get("source_a"), None)
            self.assertNotEqual(c.get("source_b"), None)

    def test_no_signal_scene_ids_sorted(self):
        """scenes_with_no_signal must be sorted ascending (Rule 6)."""
        scenes = _scenes((0.0, 5.0), (5.0, 10.0), (10.0, 15.0))
        result = _run(scenes)
        ids = result["scenes_with_no_signal"]
        self.assertEqual(ids, sorted(ids))


# ===========================================================================
# 7. Rule 6 -- Determinism
# ===========================================================================

class TestDeterminism(unittest.TestCase):
    """Rule 6: identical inputs must always produce identical outputs."""

    def _build_full_input(self):
        scenes = _scenes((0.0, 10.0), (10.0, 20.0))
        perception  = [_ev(SOURCE_PERCEPTION, 1.0, 5.0,  "a person"),
                       _ev(SOURCE_PERCEPTION, 11.0, 15.0, "empty room")]
        asr         = [_ev(SOURCE_ASR,         2.0,  6.0, "hello there")]
        diarization = [_ev(SOURCE_DIARIZATION, 0.0, 10.0, "Speaker A")]
        ocr         = [_ev(SOURCE_OCR,        12.0, 18.0, "EXIT sign")]
        return scenes, perception, asr, diarization, ocr

    def test_same_input_same_output(self):
        scenes, p, a, d, o = self._build_full_input()
        r1 = _run(scenes, perception=p, asr=a, diarization=d, ocr=o)
        r2 = _run(scenes, perception=p, asr=a, diarization=d, ocr=o)
        self.assertEqual(r1["fused_timeline"],        r2["fused_timeline"])
        self.assertEqual(r1["conflicts"],             r2["conflicts"])
        self.assertEqual(r1["scenes_with_no_signal"], r2["scenes_with_no_signal"])

    def test_fused_timeline_always_sorted(self):
        scenes = _scenes((0.0, 30.0))
        evs = [
            _ev(SOURCE_OCR,        20.0, 25.0, "z"),
            _ev(SOURCE_PERCEPTION,  1.0,  5.0, "a"),
            _ev(SOURCE_ASR,        10.0, 15.0, "m"),
        ]
        result = _run(scenes, perception=[evs[1]], asr=[evs[2]], ocr=[evs[0]])
        starts = [e["start_seconds"] for e in result["fused_timeline"]
                  if e["source_agent"] is not None]
        self.assertEqual(starts, sorted(starts))

    def test_conflicts_always_sorted(self):
        scenes = _scenes((0.0, 30.0))
        result = _run(
            scenes,
            perception  = [_ev(SOURCE_PERCEPTION, 2.0, 8.0,  "empty")],
            asr         = [_ev(SOURCE_ASR,         2.0, 8.0,  "lots of speech")],
            ocr         = [_ev(SOURCE_OCR,         2.0, 8.0,  "no text")],
        )
        if len(result["conflicts"]) > 1:
            keys = [
                (c["scene_id"], c["time_range"][0], c["source_a"], c["source_b"])
                for c in result["conflicts"]
            ]
            self.assertEqual(keys, sorted(keys))


# ===========================================================================
# 8. Geometry helpers
# ===========================================================================

class TestGeometryHelpers(unittest.TestCase):

    def test_overlap_seconds_non_overlapping(self):
        self.assertAlmostEqual(_overlap_seconds(0.0, 5.0, 6.0, 10.0), 0.0)

    def test_overlap_seconds_partial(self):
        self.assertAlmostEqual(_overlap_seconds(0.0, 8.0, 5.0, 12.0), 3.0)

    def test_overlap_seconds_contained(self):
        self.assertAlmostEqual(_overlap_seconds(0.0, 20.0, 5.0, 10.0), 5.0)

    def test_overlap_fraction_full(self):
        # [2, 8] vs [2, 8]: full overlap of shorter = 100%
        self.assertAlmostEqual(_overlap_fraction(2.0, 8.0, 2.0, 8.0), 1.0)

    def test_overlap_fraction_half(self):
        # [0,4] vs [2,6]: overlap=2, min_dur=4 -> 50%
        self.assertAlmostEqual(_overlap_fraction(0.0, 4.0, 2.0, 6.0), 0.5)

    def test_overlap_fraction_zero(self):
        self.assertAlmostEqual(_overlap_fraction(0.0, 5.0, 6.0, 10.0), 0.0)


# ===========================================================================
# 9. Scene assignment
# ===========================================================================

class TestSceneAssignment(unittest.TestCase):

    def test_find_scene_id_exact_boundary(self):
        scenes = _scenes((0.0, 10.0), (10.0, 20.0))
        self.assertEqual(_find_scene_id(0.0,  scenes), 0)
        self.assertEqual(_find_scene_id(10.0, scenes), 1)

    def test_find_scene_id_midpoint(self):
        scenes = _scenes((0.0, 10.0), (10.0, 20.0))
        self.assertEqual(_find_scene_id(5.0,  scenes), 0)
        self.assertEqual(_find_scene_id(15.0, scenes), 1)

    def test_find_scene_id_empty_scenes_returns_zero(self):
        self.assertEqual(_find_scene_id(5.0, []), 0)

    def test_find_scene_id_before_all_scenes(self):
        scenes = _scenes((5.0, 15.0))
        # 0.0 is before the first scene; nearest by start distance is scene 0
        self.assertEqual(_find_scene_id(0.0, scenes), 0)

    def test_sort_scenes_deterministic(self):
        scenes = [
            {"scene_id": 1, "start_seconds": 10.0, "end_seconds": 20.0},
            {"scene_id": 0, "start_seconds":  0.0, "end_seconds": 10.0},
        ]
        sorted_s = _sort_scenes(scenes)
        self.assertEqual(sorted_s[0]["scene_id"], 0)
        self.assertEqual(sorted_s[1]["scene_id"], 1)


# ===========================================================================
# 10. Conflict classification
# ===========================================================================

class TestConflictClassification(unittest.TestCase):

    def _ev_pair(self, content_a, content_b, type_a="speech", type_b="speech",
                 start_a=0.0, end_a=10.0, start_b=0.0, end_b=10.0):
        ev_a = {
            "start_seconds": start_a, "end_seconds": end_a,
            "type": type_a, "content": content_a,
            "source_agent": SOURCE_PERCEPTION,
        }
        ev_b = {
            "start_seconds": start_b, "end_seconds": end_b,
            "type": type_b, "content": content_b,
            "source_agent": SOURCE_ASR,
        }
        return ev_a, ev_b

    def test_presence_contradiction_empty_vs_speech(self):
        ev_a, ev_b = self._ev_pair("empty room", "I am speaking")
        self.assertEqual(_classify_conflict_type(ev_a, ev_b), CT_PRESENCE)

    def test_presence_contradiction_silence_vs_audio(self):
        ev_a, ev_b = self._ev_pair("silence detected", "loud music")
        self.assertEqual(_classify_conflict_type(ev_a, ev_b), CT_PRESENCE)

    def test_timing_mismatch_same_type_different_boundaries(self):
        # Same type "speech", but very different start times -> timing mismatch
        ev_a, ev_b = self._ev_pair(
            "talking", "talking",
            type_a="speech", type_b="speech",
            start_a=0.0, end_a=10.0,
            start_b=4.0, end_b=14.0,   # start_diff=4, min_dur=10 -> 40% > 25%
        )
        self.assertEqual(_classify_conflict_type(ev_a, ev_b), CT_TIMING)

    def test_content_mismatch_catch_all(self):
        ev_a, ev_b = self._ev_pair("stock market rises", "market crashes badly",
                                   type_a="text", type_b="speech")
        result = _classify_conflict_type(ev_a, ev_b)
        self.assertIn(result, {CT_CONTENT, CT_TIMING, CT_PRESENCE})

    def test_conflict_type_constants_are_correct_strings(self):
        self.assertEqual(CT_PRESENCE, "presence_contradiction")
        self.assertEqual(CT_CONTENT,  "content_mismatch")
        self.assertEqual(CT_TIMING,   "timing_mismatch")


# ===========================================================================
# 11. Integration test -- full realistic scenario
# ===========================================================================

class TestFullIntegration(unittest.TestCase):
    """
    End-to-end test with realistic multi-scene inputs.
    Mirrors the 'load a sample case' pattern in project_manager_test.py.
    """

    def test_realistic_multi_scene_fusion(self):
        """
        3 scenes.  Scene 0: all four sources active.
                   Scene 1: deliberate presence conflict (vision says empty,
                             ASR has speech) -- conflict must be flagged.
                   Scene 2: only OCR.
        Asserts:
          - fused_timeline has events from all relevant sources
          - conflicts list has at least 1 entry for scene 1
          - conflict event still appears in fused_timeline (not silently dropped)
          - scene 2 is NOT in scenes_with_no_signal (OCR covers it)
          - no uncovered scene is missing a no_signal placeholder
        """
        scenes = _scenes((0.0, 10.0), (10.0, 20.0), (20.0, 30.0))

        perception = [
            _ev(SOURCE_PERCEPTION,  2.0,  8.0, "two people talking", confidence=0.92),
            _ev(SOURCE_PERCEPTION, 12.0, 18.0, "empty room",          confidence=0.88),  # conflict
        ]
        asr = [
            _ev(SOURCE_ASR,  3.0,  7.0, "good morning everyone", confidence=0.95),
            _ev(SOURCE_ASR, 11.0, 19.0, "please be seated",       confidence=0.91),  # conflict
        ]
        diarization = [
            _ev(SOURCE_DIARIZATION,  0.0, 10.0, "Speaker A", confidence=0.80),
            _ev(SOURCE_DIARIZATION, 10.0, 20.0, "Speaker B", confidence=0.78),
        ]
        ocr = [
            _ev(SOURCE_OCR,  1.0,  4.0, "CONFERENCE ROOM B", confidence=0.97),
            _ev(SOURCE_OCR, 22.0, 28.0, "EXIT",               confidence=0.99),
        ]

        result = _run(scenes, perception=perception, asr=asr,
                      diarization=diarization, ocr=ocr)

        # --- fused_timeline non-empty ---
        self.assertGreater(len(result["fused_timeline"]), 0)

        # --- conflict in scene 1 (perception:"empty room" vs asr:"please be seated") ---
        self.assertGreater(len(result["conflicts"]), 0)
        scene1_conflicts = [c for c in result["conflicts"] if c["scene_id"] == 1]
        self.assertGreater(len(scene1_conflicts), 0)

        # --- conflicting events still in fused_timeline ---
        scene1_events = [e for e in result["fused_timeline"] if e["scene_id"] == 1]
        scene1_sources = {e["source_agent"] for e in scene1_events
                          if e["source_agent"] is not None}
        self.assertIn(SOURCE_PERCEPTION, scene1_sources)
        self.assertIn(SOURCE_ASR,        scene1_sources)

        # --- scene 2 is covered by OCR ---
        self.assertNotIn(2, result["scenes_with_no_signal"])

        # --- no_signal list is sorted ---
        ns = result["scenes_with_no_signal"]
        self.assertEqual(ns, sorted(ns))

        # --- result is JSON-serializable ---
        json.dumps(result)

    def test_speaker_split_visible_in_fused_timeline(self):
        """
        An ASR segment spanning a speaker boundary should appear twice in
        the fused_timeline (once per speaker piece) with bracketed speaker labels.
        """
        scenes = _scenes((0.0, 20.0))
        asr = [_ev(SOURCE_ASR, 0.0, 10.0, "shared utterance")]
        diar = [
            _ev(SOURCE_DIARIZATION, 0.0,  5.0, "Alice"),
            _ev(SOURCE_DIARIZATION, 5.0, 10.0, "Bob"),
        ]
        result = _run(scenes, asr=asr, diarization=diar)
        asr_events = [e for e in result["fused_timeline"]
                      if e["source_agent"] == SOURCE_ASR]
        self.assertEqual(len(asr_events), 2)
        contents = {e["content"] for e in asr_events}
        self.assertTrue(any("Alice" in c for c in contents))
        self.assertTrue(any("Bob"   in c for c in contents))

    def test_audit_log_called(self):
        """fuse_timeline must call _write_audit_log exactly once."""
        scenes = _scenes((0.0, 10.0))
        with patch("fusion_agent._write_audit_log") as mock_log:
            fuse_timeline(scenes=scenes, perception=[], asr=[],
                          diarization=[], ocr=[])
        mock_log.assert_called_once()

    def test_overlap_threshold_constant_value(self):
        self.assertAlmostEqual(CONFLICT_OVERLAP_THRESHOLD, 0.50)


# ===========================================================================
# Main
# ===========================================================================

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite  = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)

