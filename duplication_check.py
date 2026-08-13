"""
duplication_check.py
====================
Chorus Duplication Check — Perceptual Hashing Pipeline Gate.

Pipeline position: Step 2 (runs immediately after ingest, before any AI analysis).
If ANY duplication is detected the pipeline is HALTED and a structured JSON
report is returned.  Downstream modules (quality_gate, ASR, OCR, etc.) are
NOT invoked.

Supported source types
----------------------
  youtube       — YouTube watch URL (or any yt-dlp-supported URL).
                  yt-dlp resolves the best direct stream URL; OpenCV reads frames
                  from the stream without downloading the full file.

  local_upload  — Local video file path (.mp4, .mkv, .avi, .mov, …).
                  OpenCV reads frames and enriches output with codec / resolution /
                  FPS metadata.

  live_rtsp     — Live RTSP stream URL (rtsp://…).
                  A dedicated background thread keeps the OpenCV buffer drained
                  (avoids stale-frame accumulation).  Auto-reconnect on drop.
                  Sliding-window hash comparison instead of full-history O(n²).

Perceptual hash algorithms
--------------------------
  phash  (default) — DCT-based; robust to resize, JPEG artefacts, slight colour shifts.
  dhash            — Gradient-based; fast, low false-positive rate for near-identical frames.
  ahash            — Average-hash; simplest, fastest, least discriminative.
  whash            — Wavelet-based; best against heavy compression / low-quality streams.

Duplicate detection strategies
-------------------------------
  consecutive (default) — Compare each frame only against its immediate predecessor.
                          O(n) time.  Recommended for all three source types.
  global                — Compare each frame against ALL frames in the current sliding
                          window.  O(n·W) time.  Use only for short clips / archive dedup.

Scene-change awareness
----------------------
  A scene boundary is detected when two consecutive frame hashes differ by more than
  scene_change_threshold (default 15 bits).  The comparison window resets at each
  boundary, preventing cross-scene near-duplicates from being flagged as duplicates.

Usage (CLI)
-----------
  # Local video
  python duplication_check.py --source-type local_upload --video clip.mp4 --pretty

  # YouTube URL (requires yt-dlp + internet)
  python duplication_check.py --source-type youtube --url "https://youtu.be/ID" --pretty

  # Live RTSP stream (runs for up to 60 seconds)
  python duplication_check.py --source-type live_rtsp --url "rtsp://cam/stream" --max-seconds 60 --pretty

Usage (library)
---------------
  from duplication_check import run_duplication_check

  result = run_duplication_check(
      source_type="local_upload",
      video_path="clip.mp4",
      algo="phash",
      sample_rate=2,
  )
  if result["halt_pipeline"]:
      raise RuntimeError(result["halt_reason"])
"""

import os
import sys
import json
import time
import logging
import argparse
import threading
import datetime
from collections import deque
from pathlib import Path
from typing import Optional, Iterator, Tuple

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log = logging.getLogger("chorus.duplication_check")
logging.basicConfig(
    level=logging.INFO,
    format="[duplication_check] %(levelname)s — %(message)s",
)

# ---------------------------------------------------------------------------
# Lazy dependency helpers
# ---------------------------------------------------------------------------

def _require_cv2():
    try:
        import cv2
        return cv2
    except ImportError:
        sys.exit(
            "[duplication_check] opencv-python-headless is required.\n"
            "  pip install opencv-python-headless"
        )


def _require_imagehash():
    try:
        import imagehash
        return imagehash
    except ImportError:
        sys.exit(
            "[duplication_check] imagehash is required.\n"
            "  pip install imagehash"
        )


def _require_pil():
    try:
        from PIL import Image
        return Image
    except ImportError:
        sys.exit(
            "[duplication_check] Pillow is required.\n"
            "  pip install Pillow"
        )


def _require_ytdlp():
    try:
        import yt_dlp
        return yt_dlp
    except ImportError:
        sys.exit(
            "[duplication_check] yt-dlp is required for YouTube sources.\n"
            "  pip install yt-dlp"
        )


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPPORTED_SOURCE_TYPES = ("youtube", "local_upload", "live_rtsp")
SUPPORTED_ALGOS        = ("phash", "dhash", "ahash", "whash")
SUPPORTED_DEDUP_MODES  = ("consecutive", "global")
IMAGE_EXTENSIONS       = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"}

# Empirically tuned Hamming-distance thresholds (out of 64 bits)
DEFAULT_THRESHOLDS = {
    "phash": 8,
    "dhash": 8,
    "ahash": 10,
    "whash": 8,
}

# Hamming distance above which two consecutive frames are a scene change.
# At this distance the comparison window resets.
SCENE_CHANGE_THRESHOLD = 15

# RTSP reconnect settings
RTSP_RECONNECT_SLEEP = 3     # seconds between reconnect attempts
RTSP_MAX_RETRIES     = 10    # max consecutive reconnect attempts before giving up


# ============================================================
# Section 1 — Perceptual hashing helpers
# ============================================================

def _compute_hash(image, algo: str, ih):
    """Compute a perceptual hash for a PIL Image."""
    fn = {
        "phash": ih.phash,
        "dhash": ih.dhash,
        "ahash": ih.average_hash,
        "whash": ih.whash,
    }[algo]
    return fn(image)


def _hamming(h1, h2) -> int:
    """Return Hamming distance between two imagehash objects as a plain Python int."""
    return int(h1 - h2)


# ============================================================
# Section 2 — Frame extraction (per source type)
# ============================================================

# ── 2a. VOD helper (shared by local_upload and youtube) ──────────────────

def _open_video_capture(path_or_url: str):
    """Open cv2.VideoCapture; raise FileNotFoundError if it fails to open."""
    cv2 = _require_cv2()
    cap = cv2.VideoCapture(path_or_url)
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video source: {path_or_url}")
    return cap, cv2


def _extract_vod_metadata(cap, cv2, title: Optional[str] = None) -> dict:
    """Extract standardised metadata from an open VideoCapture object."""
    fps       = cap.get(cv2.CAP_PROP_FPS) or 0.0
    width     = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height    = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_cnt = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Decode the 32-bit FOURCC codec identifier to a human-readable string
    fourcc_int = int(cap.get(cv2.CAP_PROP_FOURCC))
    codec = "".join([
        chr((fourcc_int >> (8 * i)) & 0xFF) for i in range(4)
    ]).strip()

    duration = (frame_cnt / fps) if (fps > 0 and frame_cnt > 0) else None
    return {
        "fps":              round(fps, 3),
        "width":            width,
        "height":           height,
        "total_frames":     frame_cnt if frame_cnt > 0 else None,
        "duration_seconds": round(duration, 2) if duration else None,
        "codec":            codec or "unknown",
        "title":            title,
        "resolution":       f"{width}x{height}",
    }


def _iter_vod_frames(cap, cv2, sample_rate: float):
    """
    Yield (frame_id, PIL.Image) pairs from an already-opened VideoCapture.
    sample_rate controls how many frames per second are yielded.
    frame_id = 'frame_XXXXXXXX' (zero-padded absolute frame index).
    """
    Image = _require_pil()
    fps   = cap.get(cv2.CAP_PROP_FPS) or 25.0
    step  = max(1, round(fps / sample_rate)) if sample_rate > 0 else 1

    frame_idx = 0
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_idx % step == 0:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                yield f"frame_{frame_idx:08d}", Image.fromarray(rgb)
            frame_idx += 1
    finally:
        cap.release()


# ── 2b. YouTube ───────────────────────────────────────────────────────────

def _resolve_youtube_url(yt_url: str) -> Tuple[str, dict]:
    """
    Use yt-dlp to resolve a YouTube (or any yt-dlp-supported) URL to a
    direct stream URL — no video file is downloaded.

    Returns (stream_url, yt_dlp_info_dict).
    """
    yt_dlp = _require_ytdlp()

    ydl_opts = {
        "format":      "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "quiet":       True,
        "no_warnings": True,
    }

    log.info(f"Resolving YouTube URL via yt-dlp: {yt_url}")
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(yt_url, download=False)

    # yt-dlp returns a playlist wrapper for some URLs — unwrap it
    if "entries" in info:
        info = info["entries"][0]

    stream_url = info.get("url") or info.get("webpage_url")
    if not stream_url:
        raise ValueError(f"yt-dlp could not resolve a stream URL for: {yt_url}")

    log.info(f"Resolved stream URL (first 80 chars): {stream_url[:80]}")
    return stream_url, info


def _build_youtube_metadata(info: dict) -> dict:
    """Convert a yt-dlp info dict to the standardised metadata schema."""
    fps = info.get("fps")
    w   = info.get("width")
    h   = info.get("height")
    dur = info.get("duration")
    return {
        "fps":              fps,
        "width":            w,
        "height":           h,
        "total_frames":     None,  # not available without downloading
        "duration_seconds": dur,
        "codec":            info.get("vcodec", "unknown"),
        "title":            info.get("title"),
        "resolution":       f"{w}x{h}" if w and h else None,
        "uploader":         info.get("uploader"),
        "upload_date":      info.get("upload_date"),
        "view_count":       info.get("view_count"),
        "youtube_id":       info.get("id"),
    }


# ── 2c. Live RTSP with threaded producer ─────────────────────────────────

class _RtspFrameProducer:
    """
    Background-thread frame producer for live RTSP streams.

    Design rationale
    ----------------
    OpenCV's `VideoCapture.read()` blocks until a new frame arrives.  When
    processing is slower than the stream FPS the internal buffer fills up and
    subsequent reads return stale frames.

    This class solves that by running a dedicated daemon thread that calls
    `cap.read()` continuously and stores ONLY the latest frame in a 1-slot
    deque.  The main thread calls `next_frame()` to get the freshest frame
    without blocking on I/O.

    Disconnect & reconnect
    ----------------------
    When `cap.read()` returns False the thread treats this as a stream drop,
    records a gap entry, sleeps, and re-opens `VideoCapture`.  Up to
    `max_retries` consecutive failures are allowed before the thread exits.
    """

    def __init__(self, rtsp_url: str, max_retries: int = RTSP_MAX_RETRIES):
        self.url         = rtsp_url
        self.max_retries = max_retries
        self._buf        = deque(maxlen=1)   # (wall_ts, PIL.Image)
        self._stop_evt   = threading.Event()
        self._gaps: list = []                # stream gap records
        self._reconnects = 0
        self._thread     = threading.Thread(target=self._loop, daemon=True, name="rtsp-producer")

    # ── Public API ─────────────────────────────────────────────────────────

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop_evt.set()
        self._thread.join(timeout=8)

    def next_frame(self):
        """Return (wall_ts, PIL.Image) or None if no frame is ready yet."""
        try:
            return self._buf[-1]
        except IndexError:
            return None

    @property
    def stream_gaps(self) -> list:
        return list(self._gaps)

    @property
    def reconnect_count(self) -> int:
        return self._reconnects

    # ── Background loop ────────────────────────────────────────────────────

    def _loop(self):
        cv2   = _require_cv2()
        Image = _require_pil()

        retries        = 0
        cap            = None
        gap_start_wall: Optional[float] = None

        while not self._stop_evt.is_set():

            # Open / reopen stream
            if cap is None or not cap.isOpened():
                if cap is not None:
                    cap.release()
                log.info(f"RTSP: connecting to {self.url}  (attempt {retries + 1})")
                cap = cv2.VideoCapture(self.url)

                if not cap.isOpened():
                    retries += 1
                    if retries > self.max_retries:
                        log.error("RTSP: exceeded max retries. Producer stopping.")
                        break
                    if gap_start_wall is None:
                        gap_start_wall = time.time()
                    log.warning(f"RTSP: open failed, sleeping {RTSP_RECONNECT_SLEEP}s …")
                    time.sleep(RTSP_RECONNECT_SLEEP)
                    continue

                # Successfully (re)connected — record gap
                if gap_start_wall is not None:
                    gap_end_wall = time.time()
                    gap_dur      = round(gap_end_wall - gap_start_wall, 2)
                    self._gaps.append({
                        "wall_time_start":  _ts_to_iso(gap_start_wall),
                        "wall_time_end":    _ts_to_iso(gap_end_wall),
                        "duration_seconds": gap_dur,
                    })
                    self._reconnects += 1
                    log.info(f"RTSP: reconnected after {gap_dur:.1f}s gap.")
                    gap_start_wall = None
                retries = 0

            # Read one frame
            ret, frame = cap.read()
            if not ret:
                if gap_start_wall is None:
                    gap_start_wall = time.time()
                    log.warning("RTSP: frame read failed — stream may have dropped.")
                cap.release()
                cap = None
                time.sleep(RTSP_RECONNECT_SLEEP)
                continue

            # Store latest frame
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self._buf.append((time.time(), Image.fromarray(rgb)))

        if cap and cap.isOpened():
            cap.release()


# ============================================================
# Section 3 — Helpers
# ============================================================

def _ts_to_iso(ts: float) -> str:
    return datetime.datetime.utcfromtimestamp(ts).isoformat() + "Z"


def _make_frame_id_from_wall(ts: float) -> str:
    return f"frame_ts_{ts:.3f}"


# ============================================================
# Section 4 — Core hashing engine
# ============================================================

def _run_hash_loop(
    frame_iter,
    algo: str,
    threshold: int,
    scene_change_threshold: int,
    dedup_mode: str,
    window_seconds: float,
    is_live: bool,
) -> Tuple[list, list, list, float]:
    """
    Iterate over frames, compute perceptual hashes, detect duplicates and
    scene boundaries.

    frame_iter must yield one of:
      - (frame_id, PIL.Image)                         — VOD (local / youtube)
      - (wall_ts: float, frame_id, PIL.Image)         — RTSP live

    Returns
    -------
    hashes           : list of {frame_id, hash_hex, [wall_time]}
    dup_pairs        : list of {frame_a, frame_b, distance, hash_a, hash_b}
    scene_boundaries : list of frame_id strings
    elapsed          : float (wall-clock seconds for the entire loop)
    """
    ih = _require_imagehash()

    hashes:           list  = []
    dup_pairs:        list  = []
    scene_boundaries: list  = []
    window:           deque = deque()   # sliding comparison window
    prev_hash                = None
    t0                       = time.perf_counter()

    for item in frame_iter:
        # Unpack — support both 2-tuple (VOD) and 3-tuple (RTSP)
        if len(item) == 3:
            wall_ts, frame_id, image = item
        else:
            wall_ts = None
            frame_id, image = item

        h     = _compute_hash(image, algo, ih)
        h_hex = str(h)

        # ── Scene change detection ───────────────────────────────────────────
        if prev_hash is not None:
            scene_dist = _hamming(h, prev_hash)
            if scene_dist > scene_change_threshold:
                scene_boundaries.append(frame_id)
                window.clear()   # reset window — don't compare across scenes
                log.debug(f"Scene boundary detected at {frame_id} (dist={scene_dist})")

        # ── Prune window by time (RTSP) ──────────────────────────────────────
        if is_live and wall_ts is not None and window_seconds > 0:
            cutoff = wall_ts - window_seconds
            while window and window[0].get("wall_ts", 0) < cutoff:
                window.popleft()

        # ── Duplicate comparison ─────────────────────────────────────────────
        if dedup_mode == "consecutive":
            # O(1) per frame: only check against immediate predecessor
            compare_against = [window[-1]] if window else []
        else:
            # O(W) per frame: check against entire sliding window
            compare_against = list(window)

        for prev in compare_against:
            dist = _hamming(h, prev["_hash"])
            if dist <= threshold:
                dup_pairs.append({
                    "frame_a":  prev["frame_id"],
                    "frame_b":  frame_id,
                    "distance": dist,
                    "hash_a":   prev["hash_hex"],
                    "hash_b":   h_hex,
                })

        # ── Append to window ─────────────────────────────────────────────────
        win_entry = {"frame_id": frame_id, "hash_hex": h_hex, "_hash": h}
        if wall_ts is not None:
            win_entry["wall_ts"] = wall_ts
        window.append(win_entry)
        prev_hash = h

        # ── Public hashes list (no internal _hash object) ─────────────────────
        pub = {"frame_id": frame_id, "hash_hex": h_hex}
        if wall_ts is not None:
            pub["wall_time"] = _ts_to_iso(wall_ts)
        hashes.append(pub)

    elapsed = time.perf_counter() - t0
    return hashes, dup_pairs, scene_boundaries, elapsed


# ============================================================
# Section 5 — Segment aggregation & statistics
# ============================================================

def _aggregate_segments(dup_pairs: list) -> list:
    """
    Group consecutive duplicate pairs into contiguous segments.

    A segment is a maximal chain where frame_b of pair[i] == frame_a of pair[i+1].
    Each segment includes start/end frame IDs, total frame count, pair count,
    and min/max Hamming distances within the segment.
    """
    if not dup_pairs:
        return []

    segments = []
    chain    = [dup_pairs[0]]

    for pair in dup_pairs[1:]:
        if pair["frame_a"] == chain[-1]["frame_b"]:
            chain.append(pair)
        else:
            segments.append(chain)
            chain = [pair]
    segments.append(chain)

    result = []
    for seg in segments:
        frames     = [p["frame_a"] for p in seg] + [seg[-1]["frame_b"]]
        distances  = [p["distance"] for p in seg]
        result.append({
            "segment_start": frames[0],
            "segment_end":   frames[-1],
            "frame_count":   len(frames),
            "pair_count":    len(seg),
            "min_distance":  int(min(distances)),
            "max_distance":  int(max(distances)),
        })
    return result


def _build_stats(hashes, dup_pairs, segments, scene_boundaries) -> dict:
    distances = [int(p["distance"]) for p in dup_pairs]
    return {
        "total_frames_checked":     int(len(hashes)),
        "duplicate_pairs_found":    int(len(dup_pairs)),
        "duplicate_segments_found": int(len(segments)),
        "scene_boundaries_found":   int(len(scene_boundaries)),
        "min_hash_distance":        int(min(distances)) if distances else None,
        "max_hash_distance":        int(max(distances)) if distances else None,
        "avg_hash_distance":        round(sum(distances) / len(distances), 2) if distances else None,
    }


# ============================================================
# Section 6 — Public API
# ============================================================

def run_duplication_check(
    source_type:            str,
    video_path:             Optional[str] = None,
    url:                    Optional[str] = None,
    algo:                   str           = "phash",
    threshold:              Optional[int] = None,
    dedup_mode:             str           = "consecutive",
    sample_rate:            float         = 1.0,
    scene_change_threshold: int           = SCENE_CHANGE_THRESHOLD,
    window_seconds:         float         = 10.0,
    max_seconds:            float         = 300.0,
    rtsp_max_retries:       int           = RTSP_MAX_RETRIES,
    video_id:               Optional[str] = None,
) -> dict:
    """
    Run the perceptual-hash duplication check.

    Parameters
    ----------
    source_type             : "youtube" | "local_upload" | "live_rtsp"
    video_path              : Local file path — required for local_upload.
    url                     : YouTube or RTSP URL — required for youtube / live_rtsp.
    algo                    : Hash algorithm — phash | dhash | ahash | whash.
    threshold               : Hamming distance at or below which frames are duplicates.
                              Defaults to DEFAULT_THRESHOLDS[algo].
    dedup_mode              : "consecutive" (default, O(n)) or "global" (O(n·W)).
    sample_rate             : Frames per second to sample from VOD sources (default 1).
    scene_change_threshold  : Hamming distance above which a scene boundary is declared.
    window_seconds          : Rolling window duration for RTSP sliding-window dedup.
    max_seconds             : Max capture time for RTSP (default 300 s).
    rtsp_max_retries        : Max reconnect attempts for RTSP.
    video_id                : Optional identifier echoed in the result JSON.

    Returns
    -------
    dict — structured JSON-serialisable result containing:
        halt_pipeline, duplicate_found, halt_reason,
        stats, video_metadata, scene_boundaries,
        duplicate_pairs, duplicate_segments, hashes,
        elapsed_seconds.
        RTSP only: rtsp_reconnects, stream_gaps_detected.
    """
    # ── Input validation ───────────────────────────────────────────────────
    if source_type not in SUPPORTED_SOURCE_TYPES:
        raise ValueError(
            f"source_type must be one of {SUPPORTED_SOURCE_TYPES}, got '{source_type}'"
        )
    if algo not in SUPPORTED_ALGOS:
        raise ValueError(f"algo must be one of {SUPPORTED_ALGOS}, got '{algo}'")
    if dedup_mode not in SUPPORTED_DEDUP_MODES:
        raise ValueError(
            f"dedup_mode must be one of {SUPPORTED_DEDUP_MODES}, got '{dedup_mode}'"
        )
    if threshold is None:
        threshold = DEFAULT_THRESHOLDS[algo]

    # ── Source-specific ingestion ──────────────────────────────────────────
    video_metadata:       dict = {}
    stream_gaps_detected: list = []
    rtsp_reconnects:      int  = 0
    is_live:              bool = False
    producer                   = None

    if source_type == "local_upload":
        if not video_path:
            raise ValueError("video_path is required for source_type='local_upload'")
        cap, cv2       = _open_video_capture(video_path)
        video_metadata = _extract_vod_metadata(cap, cv2)
        frame_iter     = _iter_vod_frames(cap, cv2, sample_rate)
        source_desc    = f"local_upload:{video_path}"

    elif source_type == "youtube":
        if not url:
            raise ValueError("url is required for source_type='youtube'")
        stream_url, yt_info = _resolve_youtube_url(url)
        video_metadata      = _build_youtube_metadata(yt_info)
        cap, cv2            = _open_video_capture(stream_url)
        frame_iter          = _iter_vod_frames(cap, cv2, sample_rate)
        source_desc         = f"youtube:{url}"

    elif source_type == "live_rtsp":
        if not url:
            raise ValueError("url is required for source_type='live_rtsp'")
        is_live     = True
        source_desc = f"live_rtsp:{url}"

        producer = _RtspFrameProducer(url, max_retries=rtsp_max_retries)
        producer.start()
        time.sleep(1.5)   # allow producer thread to connect

        deadline      = time.time() + max_seconds
        min_gap_s     = 1.0 / max(sample_rate, 0.1)
        last_wall_cap = [None]

        def _rtsp_iter():
            while time.time() < deadline:
                item = producer.next_frame()
                if item is None:
                    time.sleep(0.05)
                    continue
                wall_ts, pil = item
                if last_wall_cap[0] is not None and (wall_ts - last_wall_cap[0]) < min_gap_s:
                    time.sleep(0.01)
                    continue
                last_wall_cap[0] = wall_ts
                yield (wall_ts, _make_frame_id_from_wall(wall_ts), pil)

        frame_iter = _rtsp_iter()

    # ── Run hash loop ──────────────────────────────────────────────────────
    hashes, dup_pairs, scene_boundaries, elapsed = _run_hash_loop(
        frame_iter             = frame_iter,
        algo                   = algo,
        threshold              = threshold,
        scene_change_threshold = scene_change_threshold,
        dedup_mode             = dedup_mode,
        window_seconds         = window_seconds,
        is_live                = is_live,
    )

    # ── Post-process RTSP ──────────────────────────────────────────────────
    if source_type == "live_rtsp" and producer is not None:
        producer.stop()
        stream_gaps_detected = producer.stream_gaps
        rtsp_reconnects      = producer.reconnect_count

    # ── Build final result ─────────────────────────────────────────────────
    segments        = _aggregate_segments(dup_pairs)
    stats           = _build_stats(hashes, dup_pairs, segments, scene_boundaries)
    duplicate_found = len(dup_pairs) > 0
    halt_pipeline   = duplicate_found

    result = {
        "video_id":               video_id,
        "source_type":            source_type,
        "source":                 source_desc,
        "algo":                   algo,
        "threshold":              threshold,
        "dedup_mode":             dedup_mode,
        "sample_rate_fps":        sample_rate,
        "scene_change_threshold": scene_change_threshold,
        "halt_pipeline":          halt_pipeline,
        "duplicate_found":        duplicate_found,
        "halt_reason": (
            f"Duplicate frames detected: {len(dup_pairs)} pair(s) across "
            f"{len(segments)} segment(s). Pipeline halted before AI analysis."
        ) if halt_pipeline else None,
        "stats":                  stats,
        "video_metadata":         video_metadata,
        "scene_boundaries":       scene_boundaries,
        "duplicate_pairs":        dup_pairs,
        "duplicate_segments":     segments,
        "hashes":                 hashes,
        "elapsed_seconds":        round(elapsed, 4),
    }

    if source_type == "live_rtsp":
        result["rtsp_reconnects"]      = rtsp_reconnects
        result["stream_gaps_detected"] = stream_gaps_detected

    return result


# ============================================================
# Section 7 — CLI
# ============================================================

def _build_cli_parser():
    p = argparse.ArgumentParser(
        description="Chorus Duplication Check — Perceptual hashing pipeline gate.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python duplication_check.py --source-type local_upload --video clip.mp4 --pretty\n"
            "  python duplication_check.py --source-type youtube --url https://youtu.be/ID --pretty\n"
            "  python duplication_check.py --source-type live_rtsp --url rtsp://cam/s --max-seconds 30 --pretty\n"
        ),
    )

    p.add_argument(
        "--source-type", required=True, choices=SUPPORTED_SOURCE_TYPES,
        metavar="TYPE",
        help="Source type: youtube | local_upload | live_rtsp",
    )

    src = p.add_mutually_exclusive_group()
    src.add_argument("--video", metavar="PATH", help="Local video file path (local_upload).")
    src.add_argument("--url",   metavar="URL",  help="YouTube or RTSP URL.")

    p.add_argument("--algo",            default="phash", choices=SUPPORTED_ALGOS,
                   help="Perceptual hash algorithm (default: phash).")
    p.add_argument("--threshold",       type=int,   default=None,
                   help="Hamming distance threshold (default per algo).")
    p.add_argument("--dedup-mode",      default="consecutive", choices=SUPPORTED_DEDUP_MODES,
                   dest="dedup_mode",
                   help="Comparison mode: consecutive (default) or global.")
    p.add_argument("--sample-rate",     type=float, default=1.0, dest="sample_rate",
                   help="Frames/second to sample from VOD sources (default: 1).")
    p.add_argument("--scene-threshold", type=int, default=SCENE_CHANGE_THRESHOLD,
                   dest="scene_threshold",
                   help=f"Hamming distance for scene boundary detection (default: {SCENE_CHANGE_THRESHOLD}).")

    # RTSP-specific
    p.add_argument("--max-seconds",    type=float, default=300.0, dest="max_seconds",
                   help="Max seconds to capture from RTSP (default: 300).")
    p.add_argument("--window-seconds", type=float, default=10.0,  dest="window_seconds",
                   help="Sliding window for RTSP dedup in seconds (default: 10).")
    p.add_argument("--rtsp-retries",   type=int,   default=RTSP_MAX_RETRIES, dest="rtsp_retries",
                   help=f"Max RTSP reconnect attempts (default: {RTSP_MAX_RETRIES}).")

    # Output
    p.add_argument("--video-id",  default=None, dest="video_id",
                   help="Optional video identifier embedded in output.")
    p.add_argument("--pretty",    action="store_true",
                   help="Pretty-print output JSON.")
    p.add_argument("--no-hashes", action="store_true", dest="no_hashes",
                   help="Omit per-frame hash list from output.")
    p.add_argument("--verbose",   action="store_true",
                   help="Enable DEBUG logging.")
    return p


if __name__ == "__main__":
    parser = _build_cli_parser()
    args   = parser.parse_args()

    if args.verbose:
        logging.getLogger("chorus.duplication_check").setLevel(logging.DEBUG)

    if args.source_type == "local_upload" and not args.video:
        parser.error("--video is required when --source-type=local_upload")
    if args.source_type in ("youtube", "live_rtsp") and not args.url:
        parser.error("--url is required when --source-type=youtube or live_rtsp")

    result = run_duplication_check(
        source_type            = args.source_type,
        video_path             = args.video,
        url                    = args.url,
        algo                   = args.algo,
        threshold              = args.threshold,
        dedup_mode             = args.dedup_mode,
        sample_rate            = args.sample_rate,
        scene_change_threshold = args.scene_threshold,
        max_seconds            = args.max_seconds,
        window_seconds         = args.window_seconds,
        rtsp_max_retries       = args.rtsp_retries,
        video_id               = args.video_id,
    )

    if args.no_hashes:
        result.pop("hashes", None)

    print(json.dumps(result, indent=2 if args.pretty else None))
    # Exit code: 0 = no duplicates (pipeline continues), 1 = halt
    sys.exit(1 if result["halt_pipeline"] else 0)
