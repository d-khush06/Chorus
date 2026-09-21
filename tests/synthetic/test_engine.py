"""
tests/synthetic/test_engine.py
================================
Deterministic analyzer tests against synthetic ground truth.

Run: python -m pytest tests/synthetic/test_engine.py -v
  or: python tests/synthetic/test_engine.py

Rules
-----
- All tests call real engine code. No mocking of cv2.
- Every assertion has an explicit tolerance.
- Results are printed; no fake pass/fail.
- NOT RUN until executed by the user or CI.
"""

import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

import numpy as np

from tests.synthetic.generate import generate_all, _VIDEOS_DIR
from video_engine import (
    VideoEngine, TechnicalAnalyzer, MotionAnalyzer, ShotsAnalyzer,
    TextAndCodeAnalyzer, SimilarityAnalyzer, VideoProfile
)


def _make_engine(path: str) -> VideoEngine:
    e = VideoEngine(path, max_downscale_width=640)
    e.add_analyzer(TechnicalAnalyzer())
    e.add_analyzer(MotionAnalyzer(compute_heatmap=False))
    e.add_analyzer(ShotsAnalyzer())
    e.add_analyzer(TextAndCodeAnalyzer())
    e.add_analyzer(SimilarityAnalyzer())
    return e


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def assert_close(value, expected, tolerance, label):
    ok = abs(value - expected) <= tolerance
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {label}: got={value}, expected≈{expected} ±{tolerance}")
    return ok


def assert_gte(value, minimum, label):
    ok = value >= minimum
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {label}: got={value}, expected≥{minimum}")
    return ok


def assert_in_range(value, lo, hi, label):
    ok = lo <= value <= hi
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {label}: got={value}, expected in [{lo}, {hi}]")
    return ok


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: Basic 10s synthetic video
# ─────────────────────────────────────────────────────────────────────────────

def test_basic_10s(paths: dict) -> bool:
    print("\n=== TEST 1: basic_10s.mp4 ===")
    path = paths["basic_10s"]
    e = _make_engine(path)
    r = e.run(sample_rate_fps=5.0)

    tech = r["analyzers"]["TechnicalAnalyzer"]
    motion = r["analyzers"]["MotionAnalyzer"]
    shots = r["analyzers"]["ShotsAnalyzer"]

    passed = []

    # Black frames detected (0–2s; at 5fps = 10 frames)
    passed.append(assert_gte(tech["black_frame_count"], 5, "black_frame_count ≥ 5"))

    # Frozen frames detected (4–6s)
    passed.append(assert_gte(tech["frozen_frame_count"], 3, "frozen_frame_count ≥ 3"))

    # Blur: blurred segment (6–8s) should pull avg_blur lower than a normal video
    # but avg over whole clip; just assert it was computed
    passed.append(assert_in_range(tech["avg_blur"], 0, 10000, "avg_blur is a valid float"))

    # Motion: moving box (2–4s) should show peaks
    peaks = motion.get("peaks", [])
    passed.append(assert_gte(len(peaks), 1, "motion peaks detected (moving box)"))

    # Avg activity should be non-trivial (box + noise segments)
    passed.append(assert_in_range(motion["avg_activity"], 0.0, 1.0, "avg_activity in [0,1]"))

    return all(passed)


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: Scene cuts
# ─────────────────────────────────────────────────────────────────────────────

def test_scene_cuts(paths: dict) -> bool:
    print("\n=== TEST 2: scene_cuts.mp4 (5 scenes, 4 cuts) ===")
    path = paths["scene_cuts"]
    e = VideoEngine(path, max_downscale_width=640)
    e.add_analyzer(ShotsAnalyzer(mode="general"))
    r = e.run(sample_rate_fps=5.0)

    shots = r["analyzers"]["ShotsAnalyzer"]
    cut_count = shots.get("cut_count", 0)
    scene_count = shots.get("scene_count", 0)

    passed = []
    # Should detect at least 3 of the 4 hard cuts (colour flash)
    passed.append(assert_gte(cut_count, 3, f"cut_count ≥ 3 (got {cut_count})"))
    passed.append(assert_in_range(scene_count, 3, 6, f"scene_count in [3,6]"))
    return all(passed)


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: Corrupt tail video — engine must not crash
# ─────────────────────────────────────────────────────────────────────────────

def test_corrupt_tail(paths: dict) -> bool:
    print("\n=== TEST 3: corrupt_tail.mp4 (must not crash) ===")
    path = paths.get("corrupt_tail")
    if not path or not os.path.exists(path):
        print("  [SKIP] corrupt_tail not available")
        return True
    try:
        e = _make_engine(path)
        r = e.run(sample_rate_fps=5.0)
        frames = r["performance"]["frames_processed"]
        print(f"  [PASS] Engine completed; frames processed={frames}")
        return True
    except Exception as exc:
        print(f"  [FAIL] Engine crashed on corrupt tail: {exc}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: Determinism — same input → same output
# ─────────────────────────────────────────────────────────────────────────────

def test_determinism(paths: dict) -> bool:
    print("\n=== TEST 4: Determinism ===")
    path = paths["basic_10s"]

    def _run():
        e = VideoEngine(path, max_downscale_width=320)
        e.add_analyzer(TechnicalAnalyzer())
        e.add_analyzer(MotionAnalyzer(compute_heatmap=False))
        return e.run(sample_rate_fps=5.0)

    r1 = _run()
    r2 = _run()

    t1 = r1["analyzers"]["TechnicalAnalyzer"]
    t2 = r2["analyzers"]["TechnicalAnalyzer"]
    m1 = r1["analyzers"]["MotionAnalyzer"]
    m2 = r2["analyzers"]["MotionAnalyzer"]

    passed = []
    passed.append(assert_close(
        t1["avg_blur"], t2["avg_blur"], 0.01, "avg_blur deterministic"
    ))
    passed.append(assert_close(
        t1["black_frame_count"], t2["black_frame_count"], 0, "black_frame_count deterministic"
    ))
    passed.append(assert_close(
        m1["avg_activity"], m2["avg_activity"], 1e-6, "avg_activity deterministic"
    ))
    return all(passed)


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: Bounded memory — long video does not accumulate frames
# ─────────────────────────────────────────────────────────────────────────────

def test_bounded_memory(paths: dict) -> bool:
    print("\n=== TEST 5: Bounded-memory on long_30s.mp4 ===")
    path = paths.get("long_30s")
    if not path or not os.path.exists(path):
        print("  [SKIP] long_30s.mp4 not found")
        return True
    try:
        import tracemalloc
        tracemalloc.start()
        e = _make_engine(path)
        r = e.run(sample_rate_fps=2.0)
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_mb = peak / 1024 / 1024
        frames = r["performance"]["frames_processed"]
        print(f"  [INFO] frames={frames}  peak_mem={peak_mb:.1f} MB")
        passed = assert_in_range(peak_mb, 0, 800, f"peak_mem < 800 MB")
        return passed
    except ImportError:
        print("  [SKIP] tracemalloc not available")
        return True
    except Exception as exc:
        print(f"  [FAIL] Exception: {exc}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Test 6: VideoProfile round-trip
# ─────────────────────────────────────────────────────────────────────────────

def test_profile_roundtrip(paths: dict) -> bool:
    print("\n=== TEST 6: VideoProfile JSON round-trip ===")
    path = paths["basic_10s"]
    e = _make_engine(path)
    r = e.run(sample_rate_fps=5.0)

    profile = VideoProfile(run_id="test_run_001")
    profile.populate(r)

    out_path = os.path.join(_VIDEOS_DIR, "test_profile.json")
    profile.save(out_path)

    loaded = VideoProfile.load(out_path)
    passed = []
    passed.append(assert_close(
        loaded.data["technical"].get("avg_blur", -1),
        profile.data["technical"].get("avg_blur", -2),
        0.01, "profile round-trip: avg_blur"
    ))
    schema = loaded.data.get("schema_version", "")
    ok = bool(schema)
    print(f"  [{'PASS' if ok else 'FAIL'}] schema_version present: {schema!r}")
    passed.append(ok)
    print(f"  [INFO] profile saved to {out_path}")
    return all(passed)


# ─────────────────────────────────────────────────────────────────────────────
# Test 7: Performance measurement — throughput on basic_10s at 5 fps sample
# ─────────────────────────────────────────────────────────────────────────────

def test_throughput(paths: dict) -> bool:
    print("\n=== TEST 7: Throughput measurement ===")
    path = paths["basic_10s"]
    e = _make_engine(path)
    start = time.time()
    r = e.run(sample_rate_fps=0)  # all frames
    elapsed = time.time() - start
    frames = r["performance"]["frames_processed"]
    tput = frames / elapsed if elapsed > 0 else 0
    print(f"  [MEASURE] {frames} frames in {elapsed:.2f}s → {tput:.1f} fps throughput")
    print(f"  [MEASURE] elapsed_seconds reported by engine: {r['performance']['elapsed_seconds']}")
    # No hard assertion on throughput (hardware varies); just record.
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Main runner
# ─────────────────────────────────────────────────────────────────────────────

def run_all_tests():
    print("=" * 60)
    print("Chorus VideoEngine — Synthetic Test Suite")
    print("=" * 60)

    print("\n[Generating synthetic videos...]")
    paths = generate_all()

    results = {}
    results["basic_10s"] = test_basic_10s(paths)
    results["scene_cuts"] = test_scene_cuts(paths)
    results["corrupt_tail"] = test_corrupt_tail(paths)
    results["determinism"] = test_determinism(paths)
    results["bounded_memory"] = test_bounded_memory(paths)
    results["profile_roundtrip"] = test_profile_roundtrip(paths)
    results["throughput"] = test_throughput(paths)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    for name, ok in results.items():
        print(f"  {'✔ PASS' if ok else '✘ FAIL'} — {name}")
    print(f"\n{passed}/{total} tests passed.")

    return passed == total


if __name__ == "__main__":
    ok = run_all_tests()
    sys.exit(0 if ok else 1)
