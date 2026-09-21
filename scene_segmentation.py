"""
scene_segmentation.py
=====================
Chorus Pipeline -- Stage 7: Scene Segmentation Agent

Pipeline position
-----------------
  Runs AFTER : Deduplication Check (3), Manipulation Detection (4)
  Runs BEFORE : Perception & Understanding Agent (8),
                Geo-estimation Agent (7a, cyber mode only)
  Depends on  : A validated, non-duplicate video file being available.

Purpose
-------
Detect shot/scene cuts in the ingested video and produce a scene list
that ALL downstream agents (Perception, Geo-estimation, Correlation,
Fusion) key their timestamps against.

This stage is INTENTIONALLY deterministic -- the same video_path with
the same detector / threshold settings must always produce identical
scene boundaries.  Any observed non-determinism is a BUG.

Detector selection (Rule 1)
---------------------------
  cyber mode + handheld/bodycam/security footage
      -> AdaptiveDetector  (tolerates camera shake without false cuts)
  all other cases
      -> ContentDetector   (standard, reliable default)

Sensitivity (Rule 2)
--------------------
  ContentDetector threshold = 27.0  (global constant CONTENT_THRESHOLD)
  This value MUST NOT be tuned per-video.  Change CONTENT_THRESHOLD
  only after validating against a representative sample set.

Minimum scene length (Rule 3)
------------------------------
  Any cut that would produce a scene < MIN_SCENE_DURATION_S (0.6 s) is
  dropped.  Sub-0.6 s scenes are almost always compression artefacts or
  flash frames, not real scene changes.

Live RTSP (Rule 4)
------------------
  Never run detection on an open-ended live stream directly.
  Buffer into RTSP_CHUNK_SECONDS (30 s) fixed-length chunks; run
  detection per chunk; offset timestamps by the chunk's absolute stream
  position so scene_id/timestamps stay consistent with the fused timeline.

Empty result fallback (Rule 5)
-------------------------------
  If zero cuts are detected return exactly one scene spanning the full
  video duration.  Every downstream agent requires at least one scene.

Usage (library)
---------------
  from scene_segmentation import detect_scenes

  result = detect_scenes({
      "video_path": "clip.mp4",
      "source_type": "local_upload",
      "mode": "general",
  })
  # -> {"scenes": [...], "detector_used": "content", "source_type": "local_upload"}

Usage (CLI)
-----------
  python scene_segmentation.py --video clip.mp4 --source-type local_upload --mode general --pretty
  python scene_segmentation.py --video clip.mp4 --source-type local_upload --mode cyber --pretty
  python scene_segmentation.py --url  rtsp://cam/stream --source-type live_rtsp --mode general --pretty
"""

import os
import sys
import json
import time
import logging
import argparse
import datetime
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log = logging.getLogger("chorus.scene_segmentation")
logging.basicConfig(
    level=logging.INFO,
    format="[scene_segmentation] %(levelname)s -- %(message)s",
)

# ---------------------------------------------------------------------------
# Named constants -- the ONLY place these values live.
# Do NOT shadow or override them inside functions.
# ---------------------------------------------------------------------------

# Rule 2: ContentDetector sensitivity.  Fixed deployment default.
CONTENT_THRESHOLD: float = 27.0

# Rule 3: Minimum scene length in seconds.  Cuts producing shorter scenes are discarded.
MIN_SCENE_DURATION_S: float = 0.6

# Rule 4: RTSP chunk length in seconds.
RTSP_CHUNK_SECONDS: float = 30.0

# Audit log directory
AUDIT_LOG_DIR = os.path.join(os.path.dirname(__file__), "audit_logs", "step7")

# Source types accepted by this module
VALID_SOURCE_TYPES = {"youtube", "local_upload", "live_rtsp"}

# Valid operating modes
VALID_MODES = {"general", "cyber"}

# ---------------------------------------------------------------------------
# Dependency guard
# ---------------------------------------------------------------------------
try:
    from scenedetect import open_video, SceneManager  # type: ignore
    from scenedetect.detectors import ContentDetector, AdaptiveDetector  # type: ignore
    _PYSCENEDETECT_AVAILABLE = True
except ImportError:
    # Expose stub names so unittest.mock.patch can target them even when the
    # library is absent.  Any function that uses these will raise RuntimeError
    # via the _PYSCENEDETECT_AVAILABLE guard before reaching them.
    open_video       = None  # type: ignore[assignment]
    SceneManager     = None  # type: ignore[assignment]
    ContentDetector  = None  # type: ignore[assignment]
    AdaptiveDetector = None  # type: ignore[assignment]
    _PYSCENEDETECT_AVAILABLE = False
    log.warning(
        "PySceneDetect is not installed.  "
        "Install it with:  pip install scenedetect[opencv]"
    )

# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def _validate_input(payload: dict) -> Tuple[str, str, str]:
    """
    Validate and extract (video_path, source_type, mode) from the payload.

    Raises
    ------
    ValueError  -- on missing or invalid fields.

    Returns
    -------
    (video_path, source_type, mode)
    """
    video_path  = payload.get("video_path", "")
    source_type = payload.get("source_type", "")
    mode        = payload.get("mode", "general")

    if not video_path:
        raise ValueError("'video_path' is required and must not be empty.")

    if source_type not in VALID_SOURCE_TYPES:
        raise ValueError(
            f"'source_type' must be one of {sorted(VALID_SOURCE_TYPES)}; "
            f"got {source_type!r}."
        )

    if mode not in VALID_MODES:
        raise ValueError(
            f"'mode' must be one of {sorted(VALID_MODES)}; got {mode!r}."
        )

    return video_path, source_type, mode


# ---------------------------------------------------------------------------
# Detector selection (Rule 1)
# ---------------------------------------------------------------------------

def _select_detector(mode: str) -> Tuple[object, str]:
    """
    Apply Rule 1 to return (detector_instance, detector_label).

    Rule 1
    ------
    If mode == "cyber": use AdaptiveDetector (handles camera shake from
    handheld/bodycam/security footage without producing false cuts).
    Otherwise: use ContentDetector (standard, reliable default).

    Note: the spec states Rule 1 applies when mode == "cyber" AND source
    content is handheld/bodycam/security footage.  Because this stage
    is intentionally free of AI / LLM inference, we cannot classify
    content type at detection time.  We therefore apply the conservative,
    safe-side interpretation: cyber mode -> AdaptiveDetector always.
    This is explicitly documented here so a future content-type signal
    (e.g. from a metadata tag produced upstream) can be wired in.
    """
    if not _PYSCENEDETECT_AVAILABLE:
        raise RuntimeError(
            "PySceneDetect is not installed.  "
            "Run:  pip install scenedetect[opencv]"
        )
    if mode == "cyber":
        log.info("Rule 1 -- cyber mode: using AdaptiveDetector.")
        return AdaptiveDetector(), "adaptive"
    else:
        log.info(
            "Rule 1 -- general mode: using ContentDetector "
            f"(threshold={CONTENT_THRESHOLD})."
        )
        return ContentDetector(threshold=CONTENT_THRESHOLD), "content"


# ---------------------------------------------------------------------------
# Core scene detection on a single file (or file-like URL)
# ---------------------------------------------------------------------------

def _run_detection_on_file(
    video_path: str,
    detector: object,
) -> List[Tuple[float, float]]:
    """
    Run PySceneDetect on *video_path* using the supplied *detector*.

    Returns a list of (start_seconds, end_seconds) tuples representing
    detected scenes BEFORE Rule 3 / Rule 5 post-processing.

    Raises
    ------
    RuntimeError -- if PySceneDetect is unavailable or the video cannot
                   be opened.
    """
    if not _PYSCENEDETECT_AVAILABLE:
        raise RuntimeError(
            "PySceneDetect is not installed.  "
            "Run:  pip install scenedetect[opencv]"
        )

    log.info(f"Opening video: {video_path!r}")
    try:
        video = open_video(video_path)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to open video {video_path!r}: {exc}"
        ) from exc

    manager = SceneManager()
    manager.add_detector(detector)

    log.info("Detecting scenes ...")
    manager.detect_scenes(video)

    scene_list = manager.get_scene_list()
    log.info(f"Raw detected scenes: {len(scene_list)}")

    # Convert FrameTimecode pairs -> (start_s, end_s) float tuples
    result: List[Tuple[float, float]] = []
    for start_tc, end_tc in scene_list:
        start_s = start_tc.get_seconds()
        end_s   = end_tc.get_seconds()
        result.append((start_s, end_s))

    return result


# ---------------------------------------------------------------------------
# Rule 3: minimum scene length filter
# ---------------------------------------------------------------------------

def _apply_min_length(
    raw_scenes: List[Tuple[float, float]],
) -> List[Tuple[float, float]]:
    """
    Drop any scene whose duration is below MIN_SCENE_DURATION_S.

    When a too-short scene is dropped, the gap is absorbed into the
    preceding scene (its end_seconds is extended to the dropped scene's
    end_seconds).  If the very first scene is too short it is merged
    forward into the second scene instead.
    """
    if not raw_scenes:
        return []

    filtered: List[Tuple[float, float]] = []
    for start_s, end_s in raw_scenes:
        duration = end_s - start_s
        if duration < MIN_SCENE_DURATION_S:
            log.debug(
                f"Rule 3 -- dropping short scene "
                f"[{start_s:.3f}s - {end_s:.3f}s] "
                f"({duration:.3f}s < {MIN_SCENE_DURATION_S}s)."
            )
            if filtered:
                prev_start, _ = filtered[-1]
                filtered[-1] = (prev_start, end_s)
            else:
                filtered.append((start_s, end_s))
        else:
            if filtered:
                prev_start, prev_end = filtered[-1]
                prev_dur = prev_end - prev_start
                if prev_dur < MIN_SCENE_DURATION_S:
                    filtered[-1] = (prev_start, end_s)
                else:
                    filtered.append((start_s, end_s))
            else:
                filtered.append((start_s, end_s))

    # Final pass: remove remaining sub-threshold placeholders
    final: List[Tuple[float, float]] = [
        s for s in filtered if (s[1] - s[0]) >= MIN_SCENE_DURATION_S
    ]

    dropped = len(raw_scenes) - len(final)
    if dropped:
        log.info(f"Rule 3 -- filtered out {dropped} sub-threshold scene(s).")

    return final


# ---------------------------------------------------------------------------
# Rule 5: empty-result fallback
# ---------------------------------------------------------------------------

def _apply_empty_fallback(
    scenes: List[Tuple[float, float]],
    video_path: str,
) -> List[Tuple[float, float]]:
    """
    If *scenes* is empty, return a single scene spanning the full video.
    """
    if scenes:
        return scenes

    log.info("Rule 5 -- zero cuts detected; applying single-scene fallback.")
    duration = _get_video_duration(video_path)
    log.info(f"Rule 5 -- full-video scene: 0.0 - {duration:.3f}s")
    return [(0.0, duration)]


def _get_video_duration(video_path: str) -> float:
    """
    Return the duration of *video_path* in seconds using cv2.
    Falls back to 0.0 on failure so the pipeline can continue without crashing.
    """
    try:
        import cv2
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError(f"cv2 cannot open {video_path!r}")
        fps        = cap.get(cv2.CAP_PROP_FPS) or 25.0
        frame_cnt  = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        cap.release()
        if fps > 0 and frame_cnt > 0:
            return frame_cnt / fps
    except Exception as exc:
        log.warning(f"cv2 duration probe failed: {exc}")

    log.warning(
        "Could not determine video duration.  "
        "Fallback scene will span [0.0, 0.0] -- downstream agents must handle this."
    )
    return 0.0


# ---------------------------------------------------------------------------
# Build structured scene list
# ---------------------------------------------------------------------------

def _build_scene_list(
    scenes: List[Tuple[float, float]],
) -> List[dict]:
    """Convert (start_s, end_s) tuples to the canonical output dicts."""
    return [
        {
            "scene_id":      idx,
            "start_seconds": round(start_s, 3),
            "end_seconds":   round(end_s, 3),
        }
        for idx, (start_s, end_s) in enumerate(scenes)
    ]


# ---------------------------------------------------------------------------
# VOD detection path  (youtube + local_upload)
# ---------------------------------------------------------------------------

def _detect_vod(
    video_path: str,
    mode: str,
) -> Tuple[List[Tuple[float, float]], str]:
    """
    Run scene detection on a VOD video (youtube or local_upload).

    Returns
    -------
    (scene_tuples, detector_label)
    """
    detector, detector_label = _select_detector(mode)
    raw_scenes = _run_detection_on_file(video_path, detector)
    scenes     = _apply_min_length(raw_scenes)
    scenes     = _apply_empty_fallback(scenes, video_path)
    return scenes, detector_label


# ---------------------------------------------------------------------------
# RTSP chunked detection path  (Rule 4)
# ---------------------------------------------------------------------------

def _detect_rtsp(
    rtsp_url: str,
    mode: str,
    chunk_seconds: float = RTSP_CHUNK_SECONDS,
) -> Tuple[List[Tuple[float, float]], str]:
    """
    Rule 4 implementation: buffer the live stream into fixed-length chunks
    and run detection per chunk.  Each chunk's timestamps are offset by the
    chunk's absolute position in the stream so scene_id / timestamps remain
    consistent with the fused timeline.

    Parameters
    ----------
    rtsp_url      : RTSP URL (rtsp://...)
    mode          : "general" | "cyber"
    chunk_seconds : Duration of each buffered chunk (default RTSP_CHUNK_SECONDS)

    Returns
    -------
    (scene_tuples, detector_label)
    """
    try:
        import cv2
    except ImportError:
        raise RuntimeError(
            "OpenCV (cv2) is required for RTSP capture.  pip install opencv-python"
        )

    log.info(
        f"Rule 4 -- RTSP mode.  Buffering stream into "
        f"{chunk_seconds}s chunks: {rtsp_url!r}"
    )

    detector_label = "adaptive" if mode == "cyber" else "content"

    all_scenes: List[Tuple[float, float]] = []
    stream_offset: float  = 0.0
    chunk_index:   int    = 0

    # Auto-map Wowza Cloud RTSP ingest entrypoints to direct native HLS playback
    if "cloud.wowza.com" in rtsp_url and (rtsp_url.startswith("rtsp://") or rtsp_url.startswith("rtsps://")):
        try:
            from urllib.parse import urlparse
            u = urlparse(rtsp_url)
            rtsp_url = f"http://{u.netloc}{u.path}{'' if u.path.endswith('.m3u8') else '/playlist.m3u8'}"
            log.info(f"Auto-mapped Wowza Cloud RTSP to native HLS: {rtsp_url}")
        except Exception:
            pass

    cap = cv2.VideoCapture(rtsp_url)
    if not cap.isOpened():
        raise RuntimeError(
            f"Cannot open RTSP stream: {rtsp_url!r}.  "
            "Ensure the stream is active and accessible."
        )

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frames_per_chunk = int(fps * chunk_seconds)
    log.info(f"Stream FPS: {fps:.2f}  |  Frames per chunk: {frames_per_chunk}")

    try:
        while True:
            # Collect one chunk of frames
            chunk_frames = []
            for _ in range(frames_per_chunk):
                ret, frame = cap.read()
                if not ret:
                    log.info("RTSP stream ended or read failed -- stopping capture.")
                    break
                chunk_frames.append(frame)

            if not chunk_frames:
                break

            actual_chunk_s = len(chunk_frames) / fps

            # Write chunk to a temp file, detect, then offset timestamps
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_f:
                tmp_path = tmp_f.name

            try:
                fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                h, w   = chunk_frames[0].shape[:2]
                writer = cv2.VideoWriter(tmp_path, fourcc, fps, (w, h))
                for frm in chunk_frames:
                    writer.write(frm)
                writer.release()

                # Fresh detector per chunk (stateless -> deterministic)
                detector, _ = _select_detector(mode)
                raw_chunk   = _run_detection_on_file(tmp_path, detector)
                filtered    = _apply_min_length(raw_chunk)

                if not filtered:
                    # Rule 5 per-chunk fallback
                    log.info(
                        f"Rule 5 (chunk {chunk_index}) -- no cuts detected; "
                        "whole chunk is one scene."
                    )
                    filtered = [(0.0, actual_chunk_s)]

                # Apply stream offset (Rule 4 requirement)
                for start_s, end_s in filtered:
                    all_scenes.append(
                        (stream_offset + start_s, stream_offset + end_s)
                    )

                log.info(
                    f"Chunk {chunk_index}: offset={stream_offset:.1f}s  "
                    f"scenes={len(filtered)}"
                )

            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

            stream_offset += actual_chunk_s
            chunk_index   += 1

    finally:
        cap.release()

    # Rule 5 -- global fallback if entire stream had zero scenes
    if not all_scenes:
        log.info("Rule 5 -- RTSP produced zero scenes globally; single fallback scene.")
        all_scenes = [(0.0, stream_offset if stream_offset > 0 else 0.0)]

    return all_scenes, detector_label


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------

def _write_audit_log(payload: dict, result: dict) -> None:
    """Append an audit record to the JSONL audit log for Stage 7."""
    try:
        os.makedirs(AUDIT_LOG_DIR, exist_ok=True)
        today     = datetime.date.today().isoformat()
        log_path  = os.path.join(AUDIT_LOG_DIR, f"{today}.jsonl")
        record    = {
            "timestamp":    datetime.datetime.utcnow().isoformat() + "Z",
            "input":        payload,
            "output":       result,
        }
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        log.info(f"Audit log written: {log_path}")
    except Exception as exc:
        log.warning(f"Audit log write failed (non-fatal): {exc}")


# ---------------------------------------------------------------------------
# Public entry-point
# ---------------------------------------------------------------------------

def detect_scenes(payload: dict) -> dict:
    """
    Stage 7 entry point.

    Parameters
    ----------
    payload : dict
        {
            "video_path":  "<path or URL>",      # required
            "source_type": "youtube | local_upload | live_rtsp",
            "mode":        "general | cyber",
        }

    Returns
    -------
    {
        "scenes": [
            {"scene_id": 0, "start_seconds": 0.0, "end_seconds": 12.4},
            ...
        ],
        "detector_used": "content" | "adaptive",
        "source_type":   "youtube" | "local_upload" | "live_rtsp",
    }

    Rules applied
    -------------
    Rule 1 -- Detector selection   (cyber -> adaptive, else -> content)
    Rule 2 -- Threshold fixed at CONTENT_THRESHOLD (27.0)
    Rule 3 -- Min scene length MIN_SCENE_DURATION_S (0.6 s)
    Rule 4 -- RTSP chunked detection with timestamp offsets
    Rule 5 -- Empty result fallback (always at least one scene)
    Rule 6 -- Determinism: no per-video parameter variation

    Raises
    ------
    ValueError   -- on invalid input (missing or bad fields)
    RuntimeError -- on unrecoverable detection errors
    """
    started_at = datetime.datetime.utcnow().isoformat() + "Z"

    # Input validation
    video_path, source_type, mode = _validate_input(payload)

    log.info(
        f"Stage 7 -- scene detection starting.  "
        f"source_type={source_type!r}  mode={mode!r}  "
        f"video_path={video_path!r}"
    )

    # Detection
    if source_type == "live_rtsp":
        scenes, detector_label = _detect_rtsp(video_path, mode)
    else:
        scenes, detector_label = _detect_vod(video_path, mode)

    # Build output
    result = {
        "scenes":        _build_scene_list(scenes),
        "detector_used": detector_label,
        "source_type":   source_type,
    }

    log.info(
        f"Stage 7 complete.  "
        f"scenes={len(result['scenes'])}  "
        f"detector={detector_label!r}  "
        f"started_at={started_at}"
    )

    # Audit log
    _write_audit_log(payload, result)

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Chorus Stage 7 -- Scene Segmentation Agent (PySceneDetect).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scene_segmentation.py "
            "--video clip.mp4 --source-type local_upload --mode general --pretty\n"
            "  python scene_segmentation.py "
            "--video clip.mp4 --source-type local_upload --mode cyber --pretty\n"
            "  python scene_segmentation.py "
            "--url rtsp://cam/stream --source-type live_rtsp --mode general --pretty\n"
        ),
    )

    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--video", metavar="PATH",
        help="Local video file or resolved YouTube stream URL.",
    )
    src.add_argument(
        "--url", metavar="URL",
        help="RTSP stream URL (rtsp://...).",
    )

    p.add_argument(
        "--source-type", required=True,
        choices=("youtube", "local_upload", "live_rtsp"),
        dest="source_type",
        help="Source type of the video.",
    )
    p.add_argument(
        "--mode", default="general",
        choices=("general", "cyber"),
        help="Operating mode (default: general).",
    )
    p.add_argument(
        "--pretty", action="store_true",
        help="Pretty-print the JSON output.",
    )
    p.add_argument(
        "--input", metavar="JSON_FILE",
        help=(
            "Path to a JSON file containing the full payload "
            "{'video_path', 'source_type', 'mode'}.  "
            "Overrides --video/--url, --source-type, and --mode."
        ),
    )

    return p


if __name__ == "__main__":
    parser = _build_parser()
    args   = parser.parse_args()

    if args.input:
        with open(args.input, "r", encoding="utf-8-sig") as f:
            payload = json.load(f)
    else:
        video_path = args.video or args.url
        payload = {
            "video_path":  video_path,
            "source_type": args.source_type,
            "mode":        args.mode,
        }

    try:
        result = detect_scenes(payload)
    except (ValueError, RuntimeError) as exc:
        log.error(str(exc))
        sys.exit(1)

    print(json.dumps(result, indent=2 if args.pretty else None))
    sys.exit(0)
