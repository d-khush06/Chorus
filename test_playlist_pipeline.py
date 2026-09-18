# -*- coding: utf-8 -*-
"""
test_playlist_pipeline.py
=========================
Offline smoke tests for the playlist / multi-video batch orchestration in
pipeline_runner.py. No network, no GPU, no model loads — all heavy deps are
monkeypatched (stubbed) so the tests verify orchestration logic only.

Run:
    python -m pytest test_playlist_pipeline.py -v
    python test_playlist_pipeline.py          # plain runner fallback
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import pipeline_runner as pr


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURES / STUBS
# ─────────────────────────────────────────────────────────────────────────────

FAKE_PLAYLIST = [
    {"url": f"https://www.youtube.com/watch?v=vid{i:02d}",
     "title": f"Video {i}", "video_id": f"vid{i:02d}"}
    for i in range(1, 95)  # 94 videos, like the real catalog
]


def _ok_video_result(entry):
    """A successful per-video run_full_pipeline result (minimal shape)."""
    return {
        "pipeline_halted": False,
        "halt_reason": None,
        "halt_step": None,
        "mode": "general",
        "source_type": "youtube",
        "source_uri": entry["url"],
        "user_question": "test question",
        "routing_decision": {"mode": "general", "tool_calls": ["scene_segmentation", "perception_agent", "asr_agent", "fusion_agent", "domain_output"], "excluded": [], "reasoning_summary": "stub", "routing_method": "rule_based"},
        "started_at": "2026-01-01T00:00:00Z",
        "completed_at": "2026-01-01T00:01:00Z",
        "duplication_result": {"halt_pipeline": False},
        "quality_gate_result": {"overall_verdict": "PASS"},
        "manipulation_result": {"verdict": "CLEAN"},
        "scene_result": {"scenes": [{"scene_id": 0, "start_s": 0.0, "end_s": 60.0}]},
        "vl_output": "A person teaching English on a whiteboard.",
        "asr_result": {
            "error": None,
            "language": "en",
            "word_count": 42,
            "full_transcript": "Hello class, today we learn greetings.",
            "segments": [],
        },
        "fusion_result": {"timeline": []},
        "domain_output": None,   # skipped in batch mode
        "acoustic_result": None,
        "geo_result": None,
        "face_reid_result": None,
        "alert_result": None,
        "review_queue_result": None,
        "verification_result": {"reverse_search": None, "upload_history": None, "fact_check": None, "web_search": None},
        "playlist_manifest": None,
        "analyzed_video_info": None,
    }


class _PlaylistBatchHarness:
    """Patches chorus_input + run_full_pipeline for offline batch tests."""

    def __init__(self, fail_on_urls=(), halt_on_urls=()):
        self.fail_on_urls = set(fail_on_urls)
        self.halt_on_urls = set(halt_on_urls)
        self.calls = []  # list of run_full_pipeline call kwargs

    def __enter__(self):
        self._orig_resolve = pr.__dict__.get("resolve_playlist")
        self._orig_full = pr.run_full_pipeline

        # Stub the Text Brain so batch tests never load the real 7B model
        import domain_output
        self._orig_brain = domain_output._call_text_brain

        def fake_brain(system_prompt, user_content):
            n = user_content.count("### VIDEO")
            return {
                "master_summary": f"Stub synthesis over {n} video(s).",
                "phase_topic_progression": ["stub phase"],
                "cross_video_insights": ["stub insight"],
                "content_type": "stub",
                "recommended_next_steps": [],
            }

        domain_output._call_text_brain = fake_brain

        # Patch the resolve_playlist referenced inside run_playlist_pipeline
        # (it does `from chorus_input import resolve_playlist` at call time,
        # so patch the source module).
        import chorus_input
        self._orig_ci_resolve = chorus_input.resolve_playlist

        def fake_resolve(playlist_url):
            print(f"  [resolve_playlist STUB] {len(FAKE_PLAYLIST)} video(s)")
            return list(FAKE_PLAYLIST)

        chorus_input.resolve_playlist = fake_resolve

        # Patch is_playlist_url in chorus_input too (used by __main__ only,
        # but keep it consistent).
        self._orig_ci_isplaylist = chorus_input.is_playlist_url
        chorus_input.is_playlist_url = (
            lambda u: "playlist?list=" in (u or "").lower()
        )

        def fake_full_pipeline(**kwargs):
            url = kwargs.get("url", "")
            self.calls.append(kwargs)
            if url in self.fail_on_urls:
                raise RuntimeError(f"stub: download failed for {url}")
            res = _ok_video_result({"url": url, "title": url, "video_id": url})
            if url in self.halt_on_urls:
                res["pipeline_halted"] = True
                res["halt_reason"] = "Duplicate detected (stub)"
                res["halt_step"] = "duplication_check"
            return res

        pr.run_full_pipeline = fake_full_pipeline
        return self

    def __exit__(self, *exc):
        import chorus_input
        import domain_output
        chorus_input.resolve_playlist = self._orig_ci_resolve
        chorus_input.is_playlist_url = self._orig_ci_isplaylist
        domain_output._call_text_brain = self._orig_brain
        pr.run_full_pipeline = self._orig_full
        return False


# ─────────────────────────────────────────────────────────────────────────────
# TESTS — evidence collection & heuristic synthesis (pure functions)
# ─────────────────────────────────────────────────────────────────────────────

def test_collect_multimodal_evidence_combines_asr_and_vl():
    videos = [
        {"playlist_entry": {"index": 1, "title": "Day 1", "video_id": "v1"},
         "asr_result": {"full_transcript": "transcript one"},
         "vl_output": "visual one",
         "scene_result": {"scenes": [{"scene_id": 0}]}},
        {"playlist_entry": {"index": 2, "title": "Day 2", "video_id": "v2"},
         "asr_result": {"full_transcript": "transcript two"},
         "vl_output": "visual two",
         "scene_result": {"scenes": []}},
    ]
    evidence = pr._collect_multimodal_evidence(videos)
    assert "VIDEO 1: Day 1" in evidence
    assert "VIDEO 2: Day 2" in evidence
    assert "transcript one" in evidence and "transcript two" in evidence
    assert "visual one" in evidence and "visual two" in evidence
    assert "1 scene(s)" in evidence


def test_collect_multimodal_evidence_handles_missing_fields():
    videos = [{"playlist_entry": {"index": 1, "title": "X", "video_id": "x"}}]
    evidence = pr._collect_multimodal_evidence(videos)
    assert "VIDEO 1: X" in evidence
    assert "(no visual analysis available)" in evidence
    assert "(no transcript available)" in evidence


def test_heuristic_master_summary_shape():
    videos = [
        {"playlist_entry": {"index": 1, "title": "A", "video_id": "a"},
         "asr_result": {"full_transcript": "first line topic", "word_count": 10, "language": "en"},
         "vl_output": "vl hint"},
        {"playlist_entry": {"index": 2, "title": "B", "video_id": "b"},
         "asr_result": {"full_transcript": "second topic line", "word_count": 20, "language": "hi"},
         "vl_output": None},
    ]
    h = pr._heuristic_master_summary(videos, "https://playlist")
    assert h["synthesis_method"] == "heuristic_fallback"
    assert "2 video(s)" in h["master_summary"]
    assert h["aggregate_stats"]["videos_analyzed"] == 2
    assert h["aggregate_stats"]["total_transcript_words"] == 30
    assert h["aggregate_stats"]["languages"] == ["en", "hi"]
    assert h["per_video_topics"][0]["topic_hint"] == "first line topic"


# ─────────────────────────────────────────────────────────────────────────────
# TESTS — master synthesis dispatch
# ─────────────────────────────────────────────────────────────────────────────

def test_master_synthesis_heuristic_when_disabled():
    videos = [{"playlist_entry": {"index": 1, "title": "A", "video_id": "a"},
               "asr_result": {"full_transcript": "t"}}]
    out = pr._run_master_synthesis(videos, "https://playlist", "q?",
                                   mode="general", use_text_brain=False)
    assert out["synthesis_method"] == "heuristic_fallback"


def test_master_synthesis_text_brain_success(monkeypatch):
    import domain_output

    def fake_call(system_prompt, user_content):
        assert "Master Synthesis Agent" in system_prompt
        assert "VIDEO 1" in user_content
        return {
            "master_summary": "This course teaches English in 94 days.",
            "phase_topic_progression": ["pronunciation", "tenses"],
            "cross_video_insights": ["same instructor across videos"],
            "content_type": "educational course",
            "recommended_next_steps": ["watch day 4"],
        }

    monkeypatch.setattr(domain_output, "_call_text_brain", fake_call)

    videos = [{"playlist_entry": {"index": 1, "title": "A", "video_id": "a"},
               "asr_result": {"full_transcript": "hello"}, "vl_output": "v"}]
    out = pr._run_master_synthesis(videos, "https://playlist", "q?",
                                   mode="general", use_text_brain=True)
    assert out["synthesis_method"] == "text_brain"
    assert "94 days" in out["master_summary"]
    assert out["phase_topic_progression"] == ["pronunciation", "tenses"]


def test_master_synthesis_falls_back_on_brain_error(monkeypatch):
    import domain_output

    def boom(system_prompt, user_content):
        return {"error": "Text Brain not available: no torch"}

    monkeypatch.setattr(domain_output, "_call_text_brain", boom)

    videos = [{"playlist_entry": {"index": 1, "title": "A", "video_id": "a"},
               "asr_result": {"full_transcript": "hello"}, "vl_output": "v"}]
    out = pr._run_master_synthesis(videos, "https://playlist", "q?",
                                   mode="general", use_text_brain=True)
    assert out["synthesis_method"] == "heuristic_fallback"
    assert "synthesis_error" in out


# ─────────────────────────────────────────────────────────────────────────────
# TESTS — batch orchestration
# ─────────────────────────────────────────────────────────────────────────────

def test_batch_processes_limit_and_manifest():
    with _PlaylistBatchHarness() as h:
        out = pr.run_playlist_pipeline(
            url="https://youtube.com/playlist?list=PLTEST",
            max_playlist_videos=3,
            fast_mode=True,
        )
    assert out["batch_type"] == "playlist_batch"
    assert out["total_playlist_videos"] == 94
    assert out["playlist_manifest"]["total_videos"] == 94
    assert len(out["playlist_manifest"]["videos"]) == 94
    assert len(out["analyzed_videos"]) == 3
    assert out["failed_videos"] == []
    assert len(h.calls) == 3
    # Per-video pipeline ran with domain output skipped (batch-level synthesis)
    assert all(c.get("skip_domain_output") is True for c in h.calls)
    # Master synthesis present and aggregated over 3 videos
    assert out["master_summary"] is not None
    assert out["master_summary"]["synthesis_method"] == "text_brain"
    assert out["master_summary"]["master_summary"] == "Stub synthesis over 3 video(s)."


def test_batch_max_zero_processes_all():
    with _PlaylistBatchHarness() as h:
        out = pr.run_playlist_pipeline(
            url="https://youtube.com/playlist?list=PLTEST",
            max_playlist_videos=0,
            fast_mode=True,
        )
    assert len(out["analyzed_videos"]) == 94
    assert len(h.calls) == 94
    assert out["max_playlist_videos"] == "all"


def test_batch_error_isolation_continues():
    # Video 2 raises, video 3 halts (dedup duplicate) — batch must continue
    with _PlaylistBatchHarness(
        fail_on_urls=("https://www.youtube.com/watch?v=vid02",),
        halt_on_urls=("https://www.youtube.com/watch?v=vid03",),
    ):
        out = pr.run_playlist_pipeline(
            url="https://youtube.com/playlist?list=PLTEST",
            max_playlist_videos=4,
            fast_mode=True,
        )
    statuses = [v.get("status") for v in out["analyzed_videos"]]
    assert statuses == ["ok", "failed", "failed", "ok"]
    assert len(out["failed_videos"]) == 2
    assert out["failed_videos"][0]["index"] == 2
    assert "stub: download failed" in out["failed_videos"][0]["error"]
    assert out["failed_videos"][1]["error"] == "Duplicate detected (stub)"
    # Only the 2 successful videos feed synthesis (stub counts VIDEO blocks)
    assert out["master_summary"]["master_summary"] == "Stub synthesis over 2 video(s)."


def test_batch_empty_resolution_returns_failure_record():
    with _PlaylistBatchHarness() as h:
        import chorus_input
        orig = chorus_input.resolve_playlist
        chorus_input.resolve_playlist = lambda u: []
        try:
            out = pr.run_playlist_pipeline(
                url="https://youtube.com/playlist?list=PLBROKEN",
                max_playlist_videos=3,
                fast_mode=True,
            )
        finally:
            chorus_input.resolve_playlist = orig
    assert out["total_playlist_videos"] == 0
    assert out["analyzed_videos"] == []
    assert len(out["failed_videos"]) == 1
    assert "no videos" in out["failed_videos"][0]["error"]
    assert pr.run_full_pipeline not in [None]  # harness sanity
    assert h.calls == []


def test_batch_result_is_json_serializable():
    with _PlaylistBatchHarness(
        fail_on_urls=("https://www.youtube.com/watch?v=vid02",),
    ):
        out = pr.run_playlist_pipeline(
            url="https://youtube.com/playlist?list=PLTEST",
            max_playlist_videos=2,
            fast_mode=True,
        )
    blob = json.dumps(out, ensure_ascii=False, default=str)
    assert "playlist_batch" in blob
    assert "master_summary" in blob


# ─────────────────────────────────────────────────────────────────────────────
# TESTS — CLI plumbing
# ─────────────────────────────────────────────────────────────────────────────

def test_cli_has_max_playlist_videos_arg():
    parser = pr._build_parser()
    args = parser.parse_args([
        "--url", "https://youtube.com/playlist?list=PLX",
        "--max-playlist-videos", "5",
    ])
    assert args.max_playlist_videos == 5
    # Default value
    args2 = parser.parse_args(["--video", "clip.mp4"])
    assert args2.max_playlist_videos == 3


# ─────────────────────────────────────────────────────────────────────────────
# Plain runner fallback (no pytest)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    failed = 0
    tests = [
        test_collect_multimodal_evidence_combines_asr_and_vl,
        test_collect_multimodal_evidence_handles_missing_fields,
        test_heuristic_master_summary_shape,
        test_master_synthesis_heuristic_when_disabled,
        test_master_synthesis_text_brain_success,
        test_master_synthesis_falls_back_on_brain_error,
        test_batch_processes_limit_and_manifest,
        test_batch_max_zero_processes_all,
        test_batch_error_isolation_continues,
        test_batch_empty_resolution_returns_failure_record,
        test_batch_result_is_json_serializable,
        test_cli_has_max_playlist_videos_arg,
    ]
    for t in tests:
        try:
            # Manual monkeypatch shim for the two tests using monkeypatch fixture
            if t in (test_master_synthesis_text_brain_success,
                     test_master_synthesis_falls_back_on_brain_error):
                class _MP:
                    def setattr(self, obj, name, val):
                        setattr(obj, name, val)
                    def setattr_dict(self, obj, d):
                        for k, v in d.items():
                            setattr(obj, k, v)
                # minimal: temporarily patch domain_output._call_text_brain
                import domain_output
                orig = domain_output._call_text_brain

                def _run_with_patch(fn):
                    if fn is test_master_synthesis_text_brain_success:
                        domain_output._call_text_brain = lambda s, u: {
                            "master_summary": "This course teaches English in 94 days.",
                            "phase_topic_progression": ["pronunciation", "tenses"],
                            "cross_video_insights": ["same instructor across videos"],
                            "content_type": "educational course",
                            "recommended_next_steps": ["watch day 4"],
                        }
                    else:
                        domain_output._call_text_brain = lambda s, u: {
                            "error": "Text Brain not available: no torch"}
                    try:
                        fn(_MP())
                    finally:
                        domain_output._call_text_brain = orig

                _run_with_patch(t)
            else:
                t()
            print(f"  PASS  {t.__name__}")
        except Exception as exc:
            failed += 1
            import traceback
            print(f"  FAIL  {t.__name__}: {exc}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
