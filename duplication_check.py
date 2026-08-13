"""
duplication_check.py
====================
Chorus Duplication Check — Perceptual Hashing Pipeline Gate.

This module is the second step in the Chorus pipeline.
It computes perceptual hashes of video frames and detects near-duplicate
frames/segments.  If ANY duplication is found the pipeline is HALTED
and a structured JSON report is returned before any further processing
continues.

Supports three inputs modes
---------------------------
1. Video file  : extract frames with OpenCV, hash each frame.
2. Frame dir   : read all image files from a directory, hash each one.
3. Pre-computed: accept a list of (frame_id, PIL.Image) tuples directly
                 via the Python API (useful for testing / embedding).

Supported hash algorithms
-------------------------
phash (default)  - Perceptual Hash  — best for general near-duplicate detection
dhash            - Difference Hash   — fast, low false-positive rate
ahash            - Average Hash      — simplest, least discriminative
whash            - Wavelet Hash      — robust to compression artefacts

Usage (standalone)
------------------
  python duplication_check.py --video path/to/video.mp4 --sample-rate 1
  python duplication_check.py --frames path/to/frames_dir/
  python duplication_check.py --video path/to/video.mp4 --algo dhash --threshold 8 --pretty

Usage (as a library)
--------------------
  from duplication_check import run_duplication_check
  result = run_duplication_check(video_path="video.mp4", sample_rate=1)
  if result["halt_pipeline"]:
      raise RuntimeError("Duplicates found — pipeline halted")
"""

import os
import sys
import json
import argparse
import time
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Lazy imports — opencv and imagehash are optional at import time so the
# module can be imported even if only some features are needed.
# ---------------------------------------------------------------------------

def _require_cv2():
    try:
        import cv2
        return cv2
    except ImportError:
        sys.exit("[duplication_check] opencv-python-headless is required for video input.\n"
                 "Install with: pip install opencv-python-headless")


def _require_imagehash():
    try:
        import imagehash
        return imagehash
    except ImportError:
        sys.exit("[duplication_check] imagehash is required.\n"
                 "Install with: pip install imagehash")


def _require_pil():
    try:
        from PIL import Image
        return Image
    except ImportError:
        sys.exit("[duplication_check] Pillow is required.\n"
                 "Install with: pip install Pillow")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPPORTED_ALGOS = ("phash", "dhash", "ahash", "whash")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"}

# Default Hamming-distance thresholds per algorithm (empirically tuned):
# Lower = more strict (only exact/near-exact dupes), Higher = more lenient
DEFAULT_THRESHOLDS = {
    "phash":  8,   # out of 64 bits
    "dhash":  8,
    "ahash":  10,
    "whash":  8,
}


# ---------------------------------------------------------------------------
# Core hashing helpers
# ---------------------------------------------------------------------------

def _compute_hash(image, algo: str, imagehash_mod):
    """Compute a perceptual hash for a PIL Image."""
    fn = {
        "phash": imagehash_mod.phash,
        "dhash": imagehash_mod.dhash,
        "ahash": imagehash_mod.average_hash,
        "whash": imagehash_mod.whash,
    }[algo]
    return fn(image)


def _hamming(h1, h2) -> int:
    """Return Hamming distance between two imagehash objects."""
    return h1 - h2


# ---------------------------------------------------------------------------
# Frame extraction
# ---------------------------------------------------------------------------

def _extract_frames_from_video(video_path: str, sample_rate: float):
    """
    Yield (frame_id, PIL.Image) pairs sampled at `sample_rate` frames/second.
    sample_rate=1 → one frame per second
    sample_rate=0 → every frame (very slow for long videos)
    """
    cv2  = _require_cv2()
    Image = _require_pil()

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video: {video_path}")

    fps        = cap.get(cv2.CAP_PROP_FPS) or 25.0
    step       = max(1, round(fps / sample_rate)) if sample_rate > 0 else 1
    frame_idx  = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % step == 0:
            # Convert BGR → RGB
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil = Image.fromarray(rgb)
            yield f"frame_{frame_idx:08d}", pil
        frame_idx += 1

    cap.release()


def _load_frames_from_dir(frames_dir: str):
    """Yield (filename_stem, PIL.Image) for every image in the directory."""
    Image = _require_pil()
    p = Path(frames_dir)
    files = sorted(
        f for f in p.iterdir()
        if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
    )
    for f in files:
        yield f.stem, Image.open(f).convert("RGB")


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

def _find_duplicates(frame_iter, algo: str, threshold: int):
    """
    Iterate over frames, compute hashes, and collect all duplicate pairs
    whose Hamming distance <= threshold.

    Returns
    -------
    hashes       : list of {"frame_id", "hash_hex"}
    dup_pairs    : list of {"frame_a", "frame_b", "distance", "hash_a", "hash_b"}
    elapsed_secs : float
    """
    imagehash_mod = _require_imagehash()

    hashes    = []   # [{"frame_id": str, "hash_hex": str, "_hash": obj}]
    dup_pairs = []
    t0        = time.perf_counter()

    for frame_id, image in frame_iter:
        h = _compute_hash(image, algo, imagehash_mod)
        h_hex = str(h)

        # Compare against all previously seen hashes
        for prev in hashes:
            dist = int(_hamming(h, prev["_hash"]))   # cast numpy int64 -> int
            if dist <= threshold:
                dup_pairs.append({
                    "frame_a":  prev["frame_id"],
                    "frame_b":  frame_id,
                    "distance": dist,
                    "hash_a":   prev["hash_hex"],
                    "hash_b":   h_hex,
                })

        hashes.append({"frame_id": frame_id, "hash_hex": h_hex, "_hash": h})

    elapsed = time.perf_counter() - t0

    # Strip internal _hash objects before returning
    clean_hashes = [{"frame_id": h["frame_id"], "hash_hex": h["hash_hex"]} for h in hashes]
    return clean_hashes, dup_pairs, elapsed


# ---------------------------------------------------------------------------
# Segment aggregation
# ---------------------------------------------------------------------------

def _aggregate_duplicate_segments(dup_pairs: list) -> list:
    """
    Group consecutive duplicate frame pairs into contiguous segments.
    A segment is a run where frame_b of one pair is frame_a of the next.

    Returns a list of segment dicts: {"segment_start", "segment_end", "frame_count", "min_distance"}
    """
    if not dup_pairs:
        return []

    segments  = []
    current   = [dup_pairs[0]]

    for pair in dup_pairs[1:]:
        # Consecutive if this pair's frame_a == previous pair's frame_b
        if pair["frame_a"] == current[-1]["frame_b"]:
            current.append(pair)
        else:
            segments.append(current)
            current = [pair]
    segments.append(current)

    result = []
    for seg in segments:
        all_frames = [p["frame_a"] for p in seg] + [seg[-1]["frame_b"]]
        result.append({
            "segment_start": all_frames[0],
            "segment_end":   all_frames[-1],
            "frame_count":   len(all_frames),
            "min_distance":  min(p["distance"] for p in seg),
        })
    return result


# ---------------------------------------------------------------------------
# Summary statistics
# ---------------------------------------------------------------------------

def _build_stats(hashes: list, dup_pairs: list, segments: list) -> dict:
    if dup_pairs:
        distances  = [int(p["distance"]) for p in dup_pairs]
        avg_dist   = round(sum(distances) / len(distances), 2)
        min_dist   = int(min(distances))
    else:
        avg_dist = min_dist = None

    return {
        "total_frames_checked": int(len(hashes)),
        "duplicate_pairs_found": int(len(dup_pairs)),
        "duplicate_segments_found": int(len(segments)),
        "min_hash_distance": min_dist,
        "avg_hash_distance": avg_dist,
    }


# ---------------------------------------------------------------------------
# Main public API
# ---------------------------------------------------------------------------

def run_duplication_check(
    video_path:    Optional[str]   = None,
    frames_dir:    Optional[str]   = None,
    frame_iter                     = None,   # iterable of (frame_id, PIL.Image)
    algo:          str             = "phash",
    threshold:     Optional[int]   = None,
    sample_rate:   float           = 1.0,    # frames per second (video mode only)
    video_id:      Optional[str]   = None,
) -> dict:
    """
    Run the perceptual-hash duplication check.

    Exactly ONE of video_path / frames_dir / frame_iter must be supplied.

    Parameters
    ----------
    video_path  : path to a video file (requires opencv)
    frames_dir  : path to a directory containing image files
    frame_iter  : iterable of (frame_id: str, image: PIL.Image)
    algo        : "phash" | "dhash" | "ahash" | "whash"
    threshold   : Hamming distance <= which frames are considered duplicates.
                  Defaults to DEFAULT_THRESHOLDS[algo].
    sample_rate : frames per second to sample from the video (default 1 fps)
    video_id    : optional identifier echoed back in the result

    Returns
    -------
    dict with keys:
        video_id, algo, threshold, halt_pipeline, duplicate_found,
        stats, duplicate_pairs, duplicate_segments, hashes, elapsed_seconds
    """
    if algo not in SUPPORTED_ALGOS:
        raise ValueError(f"algo must be one of {SUPPORTED_ALGOS}, got '{algo}'")

    if threshold is None:
        threshold = DEFAULT_THRESHOLDS[algo]

    # Resolve input source
    inputs_given = sum([video_path is not None, frames_dir is not None, frame_iter is not None])
    if inputs_given != 1:
        raise ValueError("Exactly one of video_path / frames_dir / frame_iter must be supplied.")

    if video_path is not None:
        iterator = _extract_frames_from_video(video_path, sample_rate)
        source_desc = f"video:{video_path}"
    elif frames_dir is not None:
        iterator = _load_frames_from_dir(frames_dir)
        source_desc = f"frames_dir:{frames_dir}"
    else:
        iterator = frame_iter
        source_desc = "frame_iter"

    # Run hashing
    hashes, dup_pairs, elapsed = _find_duplicates(iterator, algo, threshold)

    # Aggregate into segments
    segments = _aggregate_duplicate_segments(dup_pairs)

    # Build stats
    stats = _build_stats(hashes, dup_pairs, segments)

    duplicate_found = len(dup_pairs) > 0
    halt_pipeline   = duplicate_found   # always halt if any duplication found

    return {
        "video_id":           video_id,
        "source":             source_desc,
        "algo":               algo,
        "threshold":          threshold,
        "sample_rate_fps":    sample_rate,
        "halt_pipeline":      halt_pipeline,
        "duplicate_found":    duplicate_found,
        "halt_reason":        (
            f"Duplicate frames detected ({len(dup_pairs)} pairs, "
            f"{len(segments)} segment(s)). Pipeline halted."
        ) if halt_pipeline else None,
        "stats":              stats,
        "duplicate_pairs":    dup_pairs,
        "duplicate_segments": segments,
        "hashes":             hashes,
        "elapsed_seconds":    round(elapsed, 4),
    }


# ---------------------------------------------------------------------------
# CLI interface
# ---------------------------------------------------------------------------

def _build_parser():
    p = argparse.ArgumentParser(
        description="Chorus Duplication Check — Perceptual hashing pipeline gate."
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--video",  metavar="PATH", help="Path to a video file.")
    src.add_argument("--frames", metavar="DIR",  help="Path to a directory of frame images.")

    p.add_argument("--algo",        default="phash", choices=SUPPORTED_ALGOS,
                   help="Perceptual hash algorithm (default: phash).")
    p.add_argument("--threshold",   type=int, default=None,
                   help="Hamming distance threshold (default per algo).")
    p.add_argument("--sample-rate", type=float, default=1.0, dest="sample_rate",
                   help="Frames per second to sample from video (default: 1).")
    p.add_argument("--video-id",    default=None, dest="video_id",
                   help="Optional video identifier to embed in the output.")
    p.add_argument("--pretty",      action="store_true",
                   help="Pretty-print output JSON.")
    p.add_argument("--no-hashes",   action="store_true", dest="no_hashes",
                   help="Omit the per-frame hash list from output (saves space).")
    return p


if __name__ == "__main__":
    parser = _build_parser()
    args   = parser.parse_args()

    result = run_duplication_check(
        video_path  = args.video,
        frames_dir  = args.frames,
        algo        = args.algo,
        threshold   = args.threshold,
        sample_rate = args.sample_rate,
        video_id    = args.video_id,
    )

    if args.no_hashes:
        result.pop("hashes", None)

    # Exit code signals downstream tools
    # 0 = no duplicates (pipeline continues)
    # 1 = duplicates found (pipeline halted)
    print(json.dumps(result, indent=2 if args.pretty else None))
    sys.exit(1 if result["halt_pipeline"] else 0)