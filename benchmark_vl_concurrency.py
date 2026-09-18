"""
benchmark_vl_concurrency.py — Rule 6
=====================================
Empirically determines the safe max_concurrent value for process_playlist()
on the current GPU by running the worker pool at increasing concurrency levels
and measuring peak VRAM and throughput at each level.

Usage
-----
  # Use sample videos already in the project directory
  python benchmark_vl_concurrency.py

  # Use a custom folder of test videos
  python benchmark_vl_concurrency.py --video-dir /path/to/videos

  # Custom model path
  python benchmark_vl_concurrency.py --model-path ./models/Qwen2.5-VL-Agent2-Merged

Output
------
  ┌──────────────┬───────────────┬──────────────┬──────────────────┐
  │  Concurrency │  Peak VRAM GB │  Total Time  │  Throughput      │
  ├──────────────┼───────────────┼──────────────┼──────────────────┤
  │  2           │  8.41 GB      │  34.2 s      │  0.58 vids/s     │
  │  4           │  9.87 GB      │  21.7 s      │  0.92 vids/s     │
  │  6           │ OOM           │  —           │  —               │
  └──────────────┴───────────────┴──────────────┴──────────────────┘
  → Recommended max_concurrent for this GPU: 4
"""

import asyncio
import argparse
import os
import sys
import time
import glob

import torch

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

CONCURRENCY_LEVELS = [2, 4, 6, 8, 12]

# Sample video patterns to look for in the project directory
SAMPLE_PATTERNS = ["*.mp4", "*.avi", "*.mkv", "*.mov", "*.webm"]

# Number of benchmark videos (will repeat samples if fewer exist)
BENCHMARK_VIDEO_COUNT = 6

# Dummy case IDs (benchmark doesn't need real project_manager cases)
DUMMY_CASE_ID_PREFIX = "bench_case"

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def _find_sample_videos(video_dir: str, count: int) -> list:
    """Find local video files to use as benchmark samples."""
    found = []
    for pattern in SAMPLE_PATTERNS:
        found.extend(glob.glob(os.path.join(video_dir, pattern)))
    found = list(set(found))[:count]

    if not found:
        print(f"  [Benchmark] No video files found in: {video_dir}")
        print("  [Benchmark] Create dummy.mp4 or point --video-dir at a folder with videos.")
        sys.exit(1)

    # Repeat samples if fewer than requested count
    while len(found) < count:
        found.extend(found[: count - len(found)])

    return found[:count]


def _bytes_to_gb(n: int) -> float:
    return n / (1024 ** 3)


def _print_table(rows: list) -> None:
    """Print results as a formatted table."""
    header = f"{'Concurrency':>14} | {'Peak VRAM':>14} | {'Total Time':>12} | {'Throughput':>18}"
    sep    = "-" * len(header)
    print(f"\n{sep}")
    print(header)
    print(sep)
    for row in rows:
        lvl    = str(row["level"])
        vram   = f"{row['vram_gb']:.2f} GB" if row["vram_gb"] is not None else "OOM"
        t      = f"{row['time_s']:.1f} s"   if row["time_s"]  is not None else "—"
        thru   = f"{row['vids_per_s']:.2f} vids/s" if row["vids_per_s"] is not None else "—"
        print(f"{lvl:>14} | {vram:>14} | {t:>12} | {thru:>18}")
    print(sep)


# ─────────────────────────────────────────────────────────────────────────────
# MOCK PROJECT MANAGER (benchmark doesn't write real case records)
# ─────────────────────────────────────────────────────────────────────────────

class _BenchmarkProjectManager:
    """Drop-in replacement for project_manager used during benchmarking."""
    def add_artifact(self, case_id, artifact_name, artifact_bytes, actor="bench"):
        pass  # no-op — don't pollute real case store during benchmarks


def _patch_project_manager():
    """Monkey-patch the project_manager import inside run_vl_agent with the mock."""
    import sys
    from unittest.mock import MagicMock
    mock_pm = MagicMock()
    mock_pm.add_artifact = lambda *a, **kw: None
    sys.modules["project_manager"] = mock_pm


# ─────────────────────────────────────────────────────────────────────────────
# BENCHMARK RUNNER
# ─────────────────────────────────────────────────────────────────────────────

async def _run_level(video_list: list, case_ids: list, level: int, model_path: str) -> dict:
    """
    Run process_playlist at one concurrency level.
    Returns a dict with VRAM, time, and throughput — or marks OOM.
    """
    from run_vl_agent import start_vl_engine, stop_vl_engine, process_playlist

    result = {"level": level, "vram_gb": None, "time_s": None, "vids_per_s": None}

    if not torch.cuda.is_available():
        print("  [Benchmark] WARNING: No CUDA device found. VRAM measurements will be 0.")

    try:
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
            torch.cuda.empty_cache()

        print(f"\n  [Benchmark] ── Concurrency = {level} ──────────────────────────")
        start_vl_engine(model_path)

        t0 = time.perf_counter()
        results = await process_playlist(video_list, case_ids, max_concurrent=level)
        elapsed = time.perf_counter() - t0

        await stop_vl_engine()

        # Stats
        peak_vram = torch.cuda.max_memory_allocated() if torch.cuda.is_available() else 0
        n_ok      = sum(1 for r in results if r and r.get("status") != "failed")

        result["vram_gb"]    = _bytes_to_gb(peak_vram)
        result["time_s"]     = elapsed
        result["vids_per_s"] = len(video_list) / elapsed if elapsed > 0 else 0

        print(
            f"  [Benchmark] Done — {n_ok}/{len(video_list)} ok | "
            f"Peak VRAM: {result['vram_gb']:.2f} GB | "
            f"Time: {elapsed:.1f}s | "
            f"Throughput: {result['vids_per_s']:.2f} vids/s"
        )

    except torch.cuda.OutOfMemoryError:
        print(f"  [Benchmark] ⚠️  CUDA OutOfMemoryError at concurrency={level}. Stopping.")
        try:
            await stop_vl_engine()
        except Exception:
            pass
        torch.cuda.empty_cache()
        result["vram_gb"] = None  # OOM marker

    except Exception as exc:
        print(f"  [Benchmark] Unexpected error at level {level}: {exc}")
        try:
            await stop_vl_engine()
        except Exception:
            pass

    return result


async def _run_benchmark(video_paths: list, model_path: str) -> None:
    _patch_project_manager()

    video_list = [{"path": p, "user_prompt": "Describe this video briefly."} for p in video_paths]
    case_ids   = [f"{DUMMY_CASE_ID_PREFIX}_{i}" for i in range(len(video_list))]

    print(f"\n  [Benchmark] Videos: {len(video_list)} | Levels: {CONCURRENCY_LEVELS}")
    print(f"  [Benchmark] Model : {model_path}\n")

    rows = []
    best_level = None

    for level in CONCURRENCY_LEVELS:
        row = await _run_level(video_list, case_ids, level, model_path)
        rows.append(row)

        if row["vram_gb"] is None:
            print(f"  [Benchmark] OOM at concurrency={level} — stopping ladder.")
            break

        best_level = level

    _print_table(rows)

    if best_level:
        print(f"\n  ✅ Recommended max_concurrent for this GPU: {best_level}")
    else:
        print("\n  ⚠️  OOM at lowest concurrency level (2). GPU may not have enough VRAM.")
        print("      Try reducing gpu_memory_utilization in start_vl_engine().")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Benchmark vLLM playlist worker pool at increasing concurrency levels."
    )
    parser.add_argument(
        "--video-dir",
        default=".",
        help="Directory containing sample video files (default: current directory).",
    )
    parser.add_argument(
        "--model-path",
        default="",
        help="Path to VL model checkpoint (default: resolved automatically by start_vl_engine).",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=BENCHMARK_VIDEO_COUNT,
        help=f"Number of benchmark videos (default: {BENCHMARK_VIDEO_COUNT}).",
    )
    args = parser.parse_args()

    video_paths = _find_sample_videos(args.video_dir, args.count)
    print(f"  [Benchmark] Using {len(video_paths)} video(s):")
    for p in video_paths:
        print(f"    {p}")

    asyncio.run(_run_benchmark(video_paths, args.model_path))


if __name__ == "__main__":
    main()
