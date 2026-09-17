"""
geo_estimation_agent.py
=======================
Chorus Pipeline — Cyber Step C2: Geo Estimation Agent

Pipeline position
-----------------
  Runs AFTER : Scene Segmentation, VL perception (frames available)
  Runs BEFORE: Fusion Agent, Alert System
  Cyber mode only.

Purpose
-------
Predicts the most likely GPS location (lat, lon) of a scene from its imagery
using GeoCLIP, a vision model trained specifically for image geolocalisation.
This feeds the incident report with a probable area of interest.

Model
-----
  GeoCLIP (https://github.com/VicenteVivanco/GeoCLIP)
  ~1.5 GB VRAM. Runs per-frame on sampled frames.

Rules
-----
1. NEVER guess a location without the model. If GeoCLIP is unavailable the
   result is `status="unavailable"` with `error` set — a fabricated location
   is worse than no location.
2. Always report confidence and the top-k candidate list. A single coordinate
   without confidence is meaningless for forensic use.
3. Aggregate across frames with a confidence-weighted mean (circular for
   longitude) so one outlier frame cannot drag the estimate away.
4. Lazy-load the model on first call only. Never block import.
5. Never raise — on failure return an error string.

Install
-------
  pip install git+https://github.com/VicenteVivanco/GeoCLIP.git

Usage (library)
---------------
  from geo_estimation_agent import estimate_geo

  result = estimate_geo(video_path="clip.mp4")
  # result = {
  #   "status": "ok",
  #   "gps": {"lat": 51.5074, "lon": -0.1278, "confidence": 0.71},
  #   "top_predictions": [{"lat":..., "lon":..., "probability":...}, ...],
  #   "per_frame": [...],
  #   "frames_analyzed": 8,
  #   "model_used": "geoclip",
  #   "error": null
  # }

Usage (CLI)
-----------
  python geo_estimation_agent.py --video clip.mp4 --pretty
  python geo_estimation_agent.py --video clip.mp4 --top-k 5 --frames 8 --pretty
"""

import os
import sys
import json
import math
import argparse
import tempfile
import datetime
from typing import Optional

import numpy as np

# Fix Windows console encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

# Number of frames sampled from a video when only a path is supplied.
DEFAULT_FRAME_SAMPLE = int(os.getenv("GEO_FRAME_SAMPLE", "8"))

# How many candidate locations to request per frame.
DEFAULT_TOP_K = 5

# Name of the GeoCLIP model variant (passed through to the library).
GEOCLIP_MODEL_NAME = os.getenv("GEOCLIP_MODEL", "ViT-B/32")

# ─────────────────────────────────────────────────────────────────────────────
# LAZY MODEL REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

_geoclip_model = None
_geoclip_available: Optional[bool] = None


def _load_geoclip():
    """Lazy-load GeoCLIP. Returns the model or None if unavailable."""
    global _geoclip_model, _geoclip_available
    if _geoclip_available is False:
        return None
    if _geoclip_model is not None:
        return _geoclip_model

    try:
        from geoclip import GeoCLIP
    except ImportError:
        _geoclip_available = False
        print(
            "  [Geo] ⚠️  GeoCLIP not installed — geo estimation unavailable.\n"
            "  [Geo]    Install: pip install git+https://github.com/VicenteVivanco/GeoCLIP.git",
            flush=True,
        )
        return None

    try:
        print(f"  [Geo] Loading GeoCLIP ({GEOCLIP_MODEL_NAME})…", flush=True)
        _geoclip_model = GeoCLIP()
        _geoclip_available = True
        print("  [Geo] ✅ GeoCLIP loaded.", flush=True)
        return _geoclip_model
    except Exception as exc:
        _geoclip_available = False
        print(f"  [Geo] ️  GeoCLIP load failed: {exc}", flush=True)
        return None


def unload_geo_model():
    """Release GeoCLIP from VRAM."""
    global _geoclip_model
    if _geoclip_model is not None:
        try:
            del _geoclip_model
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass
        _geoclip_model = None
        print("  [Geo] GeoCLIP unloaded.", flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# FRAME SAMPLING
# ─────────────────────────────────────────────────────────────────────────────

def _sample_frames_from_video(video_path: str, num_frames: int) -> list:
    """
    Uniformly sample `num_frames` frames from a video as PIL Images.
    Returns [] on any failure.
    """
    try:
        import cv2
        from PIL import Image
    except ImportError as exc:
        print(f"  [Geo] ️  Missing dependency for frame sampling: {exc}", flush=True)
        return []

    frames = []
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"  [Geo] ⚠️  Cannot open video: {video_path}", flush=True)
        return []

    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if total <= 0:
            # Fall back to reading sequentially the first N frames
            for _ in range(num_frames):
                ok, frame = cap.read()
                if not ok:
                    break
                frames.append(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
            return frames

        step = max(total // num_frames, 1)
        idx = 0
        while len(frames) < num_frames and idx < total:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if ok:
                frames.append(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
            idx += step
        return frames
    finally:
        cap.release()


# ─────────────────────────────────────────────────────────────────────────────
# PREDICTION
# ─────────────────────────────────────────────────────────────────────────────

def _predict_frame(model, pil_image, top_k: int) -> Optional[list]:
    """
    Run GeoCLIP on one PIL image. Returns a list of
    {"lat", "lon", "probability"} or None.
    """
    tmp_path = None
    try:
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".png", prefix="chorus_geo_")
        os.close(tmp_fd)
        pil_image.convert("RGB").save(tmp_path, format="PNG")

        gps_tensor, prob_tensor = model.predict(tmp_path, top_k=top_k)

        gps = gps_tensor.detach().cpu().numpy() if hasattr(gps_tensor, "detach") \
            else np.asarray(gps_tensor)
        probs = prob_tensor.detach().cpu().numpy() if hasattr(prob_tensor, "detach") \
            else np.asarray(prob_tensor)
        probs = probs.reshape(-1)

        out = []
        for i in range(min(len(gps), len(probs))):
            out.append({
                "lat":         round(float(gps[i][0]), 6),
                "lon":         round(float(gps[i][1]), 6),
                "probability": round(float(probs[i]), 4),
            })
        return out
    except Exception as exc:
        print(f"  [Geo] ⚠️  Frame prediction failed: {exc}", flush=True)
        return None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def _circular_mean_lon(lons: np.ndarray, weights: np.ndarray) -> float:
    """Confidence-weighted circular mean of longitudes (degrees)."""
    rad = np.radians(lons)
    x = float(np.sum(weights * np.cos(rad)))
    y = float(np.sum(weights * np.sin(rad)))
    if x == 0.0 and y == 0.0:
        return float(np.average(lons, weights=weights))
    return math.degrees(math.atan2(y, x))


def _aggregate(per_frame: list) -> tuple:
    """
    Aggregate per-frame top predictions into one GPS estimate + top-k list.
    Returns (gps_dict, top_predictions_list).
    """
    valid = [pf for pf in per_frame if pf.get("predictions")]
    if not valid:
        return None, []

    # Confidence-weighted mean of the per-frame top-1 location
    top1 = [pf["predictions"][0] for pf in valid]
    lats = np.array([p["lat"] for p in top1], dtype=np.float64)
    lons = np.array([p["lon"] for p in top1], dtype=np.float64)
    weights = np.array([max(p["probability"], 1e-6) for p in top1], dtype=np.float64)

    lat_mean = float(np.average(lats, weights=weights))
    lon_mean = _circular_mean_lon(lons, weights)
    confidence = round(float(np.mean([p["probability"] for p in top1])), 4)

    # Build a top-k list by pooling candidates across frames
    pooled: dict = {}
    for pf in valid:
        for cand in pf["predictions"]:
            key = (round(cand["lat"], 3), round(cand["lon"], 3))
            entry = pooled.setdefault(key, {"lat": cand["lat"], "lon": cand["lon"],
                                            "probability": 0.0, "votes": 0})
            entry["probability"] = max(entry["probability"], cand["probability"])
            entry["votes"] += 1

    top_predictions = sorted(
        pooled.values(), key=lambda c: (c["votes"], c["probability"]), reverse=True
    )[:DEFAULT_TOP_K]
    for c in top_predictions:
        c.pop("votes", None)

    gps = {
        "lat":        round(lat_mean, 6),
        "lon":        round(lon_mean, 6),
        "confidence": confidence,
    }
    return gps, top_predictions


# ─────────────────────────────────────────────────────────────────────────────
# CORE FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def estimate_geo(
    video_path: Optional[str] = None,
    frames: Optional[list] = None,
    frame_timestamps: Optional[list] = None,
    top_k: int = DEFAULT_TOP_K,
    num_frames: int = DEFAULT_FRAME_SAMPLE,
) -> dict:
    """
    Estimate the GPS location of a video / frame set using GeoCLIP.

    Parameters
    ----------
    video_path       : Path to the video (frames sampled if `frames` not given).
    frames           : List of PIL Images (takes precedence over video_path).
    frame_timestamps : Optional list of timestamps (seconds) aligned to frames.
    top_k            : Candidate locations per frame.
    num_frames       : Number of frames to sample when using video_path.

    Returns
    -------
    dict with keys: status, gps, top_predictions, per_frame, frames_analyzed,
                    model_used, error.
    """
    started_at = datetime.datetime.utcnow().isoformat() + "Z"
    result = {
        "status":          "unavailable",
        "gps":             None,
        "top_predictions": [],
        "per_frame":       [],
        "frames_analyzed": 0,
        "model_used":      None,
        "started_at":      started_at,
        "completed_at":    None,
        "error":           None,
    }

    # ── Resolve frames ─────────────────────────────────────────────────────
    if frames is None and video_path:
        if not os.path.exists(video_path):
            result["error"] = f"File not found: {video_path}"
            print(f"  [Geo]  File not found: {video_path}", flush=True)
            return result
        print(f"  [Geo] Sampling {num_frames} frame(s) for geo estimation…", flush=True)
        frames = _sample_frames_from_video(video_path, num_frames)
    frames = frames or []

    if not frames:
        result["error"] = "No frames available for geo estimation."
        print("  [Geo] ️  No frames — skipping.", flush=True)
        return result

    # ── Load model ─────────────────────────────────────────────────────────
    model = _load_geoclip()
    if model is None:
        result["error"] = (
            "GeoCLIP not available. Install: "
            "pip install git+https://github.com/VicenteVivanco/GeoCLIP.git"
        )
        return result

    # ── Per-frame prediction ───────────────────────────────────────────────
    per_frame = []
    for i, frame in enumerate(frames):
        ts = frame_timestamps[i] if frame_timestamps and i < len(frame_timestamps) else None
        preds = _predict_frame(model, frame, top_k)
        if preds:
            per_frame.append({"frame_index": i, "timestamp_s": ts, "predictions": preds})

    result["per_frame"] = per_frame
    result["frames_analyzed"] = len(per_frame)
    result["model_used"] = "geoclip"

    if not per_frame:
        result["error"] = "GeoCLIP produced no predictions for any frame."
        print("  [Geo] ️  No predictions produced.", flush=True)
        return result

    gps, top_predictions = _aggregate(per_frame)
    result["gps"] = gps
    result["top_predictions"] = top_predictions
    result["status"] = "ok"
    result["completed_at"] = datetime.datetime.utcnow().isoformat() + "Z"

    print(
        f"  [Geo] ✅ Estimate: ({gps['lat']}, {gps['lon']}) "
        f"confidence={gps['confidence']} from {len(per_frame)} frame(s).",
        flush=True,
    )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Chorus Geo Estimation Agent — GeoCLIP image geolocalisation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python geo_estimation_agent.py --video clip.mp4 --pretty\n"
            "  python geo_estimation_agent.py --video clip.mp4 --top-k 5 --frames 10 --pretty\n"
        ),
    )
    p.add_argument("--video", required=True, help="Path to the video file.")
    p.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, dest="top_k",
                   help=f"Candidate locations per frame (default {DEFAULT_TOP_K}).")
    p.add_argument("--frames", type=int, default=DEFAULT_FRAME_SAMPLE,
                   help=f"Frames to sample (default {DEFAULT_FRAME_SAMPLE}).")
    p.add_argument("--output", default=None, help="Save JSON result to this path.")
    p.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return p


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()

    result = estimate_geo(
        video_path=args.video,
        top_k=args.top_k,
        num_frames=args.frames,
    )

    out = json.dumps(result, indent=2 if args.pretty else None,
                     ensure_ascii=False, default=str)
    print(out)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(out)
        print(f"\n  [Geo] Saved to: {args.output}", flush=True)

    sys.exit(0 if result["status"] == "ok" else 1)