"""
pipeline_runner.py
==================
Chorus Pipeline Orchestrator — runs the full Step 2 + Step 3 pipeline.

Execution order
---------------
1. Duplication Check (Step 2)
   → Perceptual-hash deduplication for the specified source.
   → If halt_pipeline = True: return combined report immediately.
     The Quality Gate is NOT invoked (no point analysing duplicate content).

2. Quality Gate (Step 3)
   → Rule-based verification of the fused timeline.
   → Returns structured verdict.

Combined output
---------------
A single JSON object containing:
  - pipeline_halted     : True if duplication check stopped the pipeline.
  - halt_reason         : Reason for halt (null if pipeline continued).
  - duplication_result  : Full output from run_duplication_check().
  - quality_gate_result : Full output from run_quality_gate()
                          (null if pipeline was halted by dedup).

Usage (standalone)
------------------
  python pipeline_runner.py \
      --source-type local_upload \
      --video clip.mp4 \
      --timeline-input timeline.json \
      --pretty

  python pipeline_runner.py \
      --source-type youtube \
      --url "https://youtu.be/ID" \
      --timeline-input timeline.json \
      --pretty

  python pipeline_runner.py \
      --source-type live_rtsp \
      --url "rtsp://cam/stream" \
      --max-seconds 60 \
      --timeline-input timeline.json \
      --pretty

Usage (library)
---------------
  from pipeline_runner import run_pipeline

  result = run_pipeline(
      dedup_kwargs={"source_type": "local_upload", "video_path": "clip.mp4"},
      quality_gate_payload=timeline_payload_dict,
  )
  print(result["pipeline_halted"])
"""

import json
import sys
import argparse
import datetime
from typing import Optional

from duplication_check import run_duplication_check
from quality_gate      import run_quality_gate


# ---------------------------------------------------------------------------
# Core orchestrator
# ---------------------------------------------------------------------------

def run_pipeline(
    dedup_kwargs:          dict,
    quality_gate_payload:  Optional[dict] = None,
) -> dict:
    """
    Run the Chorus pipeline: Duplication Check → Quality Gate.

    Parameters
    ----------
    dedup_kwargs          : kwargs dict passed directly to run_duplication_check().
                            Must include at minimum: source_type.
    quality_gate_payload  : The fused-timeline payload dict passed to run_quality_gate().
                            Required unless the pipeline is expected to halt at dedup.
                            If None and pipeline continues, quality gate is skipped.

    Returns
    -------
    dict — combined pipeline report.
    """
    started_at = datetime.datetime.utcnow().isoformat() + "Z"

    # ── Step 2: Duplication Check ──────────────────────────────────────────
    print("[pipeline_runner] Step 2 — Running duplication check …", flush=True)
    dedup_result = run_duplication_check(**dedup_kwargs)

    if dedup_result["halt_pipeline"]:
        print(
            f"[pipeline_runner] ⛔ Pipeline HALTED — {dedup_result['halt_reason']}",
            flush=True,
        )
        return {
            "pipeline_halted":      True,
            "halt_reason":          dedup_result["halt_reason"],
            "halt_step":            "duplication_check",
            "started_at":           started_at,
            "completed_at":         datetime.datetime.utcnow().isoformat() + "Z",
            "duplication_result":   dedup_result,
            "quality_gate_result":  None,
        }

    print("[pipeline_runner] ✅ Duplication check passed — no duplicates found.", flush=True)

    # ── Step 3: Quality Gate ───────────────────────────────────────────────
    quality_gate_result = None

    if quality_gate_payload is not None:
        print("[pipeline_runner] Step 3 — Running quality gate …", flush=True)
        quality_gate_result = run_quality_gate(quality_gate_payload)

        verdict = quality_gate_result.get("overall_verdict", "UNKNOWN")
        print(f"[pipeline_runner] Quality gate verdict: {verdict}", flush=True)
    else:
        print(
            "[pipeline_runner] Step 3 — No timeline payload provided; quality gate skipped.",
            flush=True,
        )

    return {
        "pipeline_halted":      False,
        "halt_reason":          None,
        "halt_step":            None,
        "started_at":           started_at,
        "completed_at":         datetime.datetime.utcnow().isoformat() + "Z",
        "duplication_result":   dedup_result,
        "quality_gate_result":  quality_gate_result,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser():
    p = argparse.ArgumentParser(
        description="Chorus Pipeline Runner — Duplication Check → Quality Gate.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python pipeline_runner.py --source-type local_upload "
            "--video clip.mp4 --timeline-input timeline.json --pretty\n"
            "  python pipeline_runner.py --source-type youtube "
            "--url https://youtu.be/ID --timeline-input tl.json --pretty\n"
        ),
    )

    # Source type
    p.add_argument(
        "--source-type", required=True,
        choices=("youtube", "local_upload", "live_rtsp"),
        help="Source type for the duplication check.",
    )

    # Video input
    src = p.add_mutually_exclusive_group()
    src.add_argument("--video", metavar="PATH", help="Local video file (local_upload).")
    src.add_argument("--url",   metavar="URL",  help="YouTube or RTSP URL.")

    # Dedup options (forwarded to run_duplication_check)
    p.add_argument("--algo",            default="phash",
                   choices=("phash", "dhash", "ahash", "whash"),
                   help="Hash algorithm (default: phash).")
    p.add_argument("--threshold",       type=int, default=None,
                   help="Hamming distance threshold.")
    p.add_argument("--dedup-mode",      default="consecutive",
                   choices=("consecutive", "global"), dest="dedup_mode",
                   help="Comparison mode (default: consecutive).")
    p.add_argument("--sample-rate",     type=float, default=1.0, dest="sample_rate",
                   help="Frames/second to sample (VOD, default: 1).")
    p.add_argument("--scene-threshold", type=int, default=15, dest="scene_threshold",
                   help="Scene change Hamming threshold (default: 15).")
    p.add_argument("--max-seconds",     type=float, default=300.0, dest="max_seconds",
                   help="Max RTSP capture time in seconds (default: 300).")
    p.add_argument("--window-seconds",  type=float, default=10.0,  dest="window_seconds",
                   help="RTSP sliding-window seconds (default: 10).")
    p.add_argument("--rtsp-retries",    type=int,   default=10, dest="rtsp_retries",
                   help="Max RTSP reconnect attempts (default: 10).")

    # Quality gate input
    p.add_argument(
        "--timeline-input", metavar="PATH", dest="timeline_input",
        help="Path to fused timeline JSON payload for the quality gate.",
    )

    # Misc
    p.add_argument("--video-id",  default=None, dest="video_id",
                   help="Optional video identifier.")
    p.add_argument("--no-hashes", action="store_true", dest="no_hashes",
                   help="Omit per-frame hashes from dedup output.")
    p.add_argument("--pretty",    action="store_true",
                   help="Pretty-print output JSON.")

    return p


if __name__ == "__main__":
    parser = _build_parser()
    args   = parser.parse_args()

    # Build dedup kwargs
    dedup_kwargs: dict = {
        "source_type":            args.source_type,
        "algo":                   args.algo,
        "threshold":              args.threshold,
        "dedup_mode":             args.dedup_mode,
        "sample_rate":            args.sample_rate,
        "scene_change_threshold": args.scene_threshold,
        "max_seconds":            args.max_seconds,
        "window_seconds":         args.window_seconds,
        "rtsp_max_retries":       args.rtsp_retries,
        "video_id":               args.video_id,
    }

    if args.source_type == "local_upload":
        if not args.video:
            parser.error("--video is required for --source-type=local_upload")
        dedup_kwargs["video_path"] = args.video
    else:
        if not args.url:
            parser.error("--url is required for youtube / live_rtsp")
        dedup_kwargs["url"] = args.url

    # Load quality gate payload
    quality_gate_payload = None
    if args.timeline_input:
        with open(args.timeline_input, "r", encoding="utf-8-sig") as f:
            quality_gate_payload = json.load(f)

    # Run pipeline
    result = run_pipeline(
        dedup_kwargs         = dedup_kwargs,
        quality_gate_payload = quality_gate_payload,
    )

    if args.no_hashes and result.get("duplication_result"):
        result["duplication_result"].pop("hashes", None)

    print(json.dumps(result, indent=2 if args.pretty else None))
    sys.exit(1 if result["pipeline_halted"] else 0)
