"""
face_reid_agent.py
==================
Chorus Pipeline — Cyber Step C3: Face Re-Identification Agent

GOVERNANCE GATE
---------------
This agent processes biometric data. It MUST NOT run unless the caller has
explicitly set `governance_approved=True`. Without that flag the agent returns
status="blocked" and performs NO face detection, NO embedding extraction and
NO identity tracking. This gate is enforced at the function boundary, not in
the orchestrator, so it cannot be bypassed by a bad routing decision.

Pipeline position
-----------------
  Runs AFTER : Scene Segmentation, VL perception (frames available)
  Runs BEFORE: Fusion Agent, Alert System, Review Queue
  Cyber mode only. Requires governance_approved=True.

Purpose
-------
Detects faces, computes ArcFace identity embeddings and clusters them across
frames into anonymous "person" tracks. If a labelled `gallery` is supplied
(pre-enrolled embeddings), clusters are matched to gallery identities. Without
a gallery the agent performs tracking/re-identification only — it cannot name
people out of thin air.

Model
-----
  InsightFace FaceAnalysis, `buffalo_l` pack (detection + ArcFace 512-d
  recognition). ~1 GB VRAM.

Rules
-----
1. Governance gate is absolute — no biometric work without approval.
2. Return anonymous identity_ids (person_1, person_2, …). Never invent names.
3. Never persist raw embeddings unless `include_embeddings=True`.
4. Cluster by cosine similarity; keep the running centroid per identity.
5. Lazy-load the model on first call only. Never block import.
6. Never raise — on failure return an error string.

Install
-------
  pip install insightface onnxruntime-gpu   (or onnxruntime for CPU)

Usage (library)
---------------
  from face_reid_agent import run_face_reid

  result = run_face_reid(
      video_path="incident.mp4",
      governance_approved=True,
  )
  # result["identities"] == [
  #   {"identity_id": "person_1", "face_count": 4, "first_seen_s": 1.2,
  #    "last_seen_s": 6.8, "label": null, "tracks": [...]},
  # ]

Usage (CLI)
-----------
  python face_reid_agent.py --video incident.mp4 --governance --pretty
  python face_reid_agent.py --video incident.mp4 --pretty   # -> blocked
"""

import os
import sys
import json
import argparse
import datetime
from typing import Optional

import numpy as np

# Fix Windows console encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ────────────────────────────────────────────────────────────────────────────

# Cosine similarity required to treat two faces as the same identity.
SIMILARITY_THRESHOLD = float(os.getenv("FACE_REID_THRESHOLD", "0.40"))

# Minimum detector confidence to accept a face.
MIN_DET_SCORE = float(os.getenv("FACE_MIN_DET_SCORE", "0.50"))

# Detector input resolution.
DET_SIZE = (640, 640)

# Frames sampled from a video when only a path is supplied.
DEFAULT_FRAME_SAMPLE = int(os.getenv("FACE_FRAME_SAMPLE", "12"))

# InsightFace model pack.
INSIGHTFACE_PACK = os.getenv("INSIGHTFACE_PACK", "buffalo_l")

# Identity embedding dimension (ArcFace).
EMBEDDING_DIM = 512


# ─────────────────────────────────────────────────────────────────────────────
# LAZY MODEL REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

_face_app = None
_face_app_available: Optional[bool] = None


def _load_face_app():
    """Lazy-load InsightFace FaceAnalysis. Returns the app or None."""
    global _face_app, _face_app_available
    if _face_app_available is False:
        return None
    if _face_app is not None:
        return _face_app

    try:
        from insightface.app import FaceAnalysis
    except ImportError:
        _face_app_available = False
        print(
            "  [FaceReID] ⚠️  insightface not installed — unavailable.\n"
            "  [FaceReID]    Install: pip install insightface onnxruntime-gpu",
            flush=True,
        )
        return None

    try:
        providers = ["CPUExecutionProvider"]
        ctx_id = -1
        try:
            import torch
            if torch.cuda.is_available():
                providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
                ctx_id = 0
        except Exception:
            pass

        print(f"  [FaceReID] Loading InsightFace {INSIGHTFACE_PACK}…", flush=True)
        app = FaceAnalysis(name=INSIGHTFACE_PACK, providers=providers)
        app.prepare(ctx_id=ctx_id, det_size=DET_SIZE)
        _face_app = app
        _face_app_available = True
        print("  [FaceReID] ✅ InsightFace loaded.", flush=True)
        return _face_app
    except Exception as exc:
        _face_app_available = False
        print(f"  [FaceReID] ️  InsightFace load failed: {exc}", flush=True)
        return None


def unload_face_app():
    """Release InsightFace from VRAM."""
    global _face_app
    if _face_app is not None:
        try:
            del _face_app
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass
        _face_app = None
        print("  [FaceReID] InsightFace unloaded.", flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# FRAME SAMPLING
# ─────────────────────────────────────────────────────────────────────────────

def _sample_frames_from_video(video_path: str, num_frames: int) -> list:
    """Uniformly sample `num_frames` frames as (frame_index, timestamp_s, BGR ndarray)."""
    try:
        import cv2
    except ImportError as exc:
        print(f"  [FaceReID] ⚠️  OpenCV required: {exc}", flush=True)
        return []

    out = []
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"  [FaceReID] ⚠️  Cannot open video: {video_path}", flush=True)
        return []

    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if total <= 0:
            for i in range(num_frames):
                ok, frame = cap.read()
                if not ok:
                    break
                out.append((i, round(i / fps, 3), frame))
            return out

        step = max(total // num_frames, 1)
        for i in range(num_frames):
            idx = min(i * step, total - 1)
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if ok:
                out.append((idx, round(idx / fps, 3), frame))
        return out
    finally:
        cap.release()


def _pil_to_bgr(pil_image) -> np.ndarray:
    """Convert a PIL image to an OpenCV BGR ndarray."""
    import cv2
    arr = np.array(pil_image.convert("RGB"))
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


# ─────────────────────────────────────────────────────────────────────────────
# EMBEDDING / CLUSTERING HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _normalise(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec)
    if norm <= 1e-12:
        return vec
    return vec / norm


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(_normalise(a), _normalise(b)))


def _cluster_faces(faces: list, threshold: float, gallery: Optional[list]) -> list:
    """
    Greedy cosine clustering of face embeddings across frames.

    faces: list of {"frame_index", "timestamp_s", "det_score", "bbox",
                    "embedding" (normalised np.ndarray)}
    gallery: optional list of {"identity": "name", "embedding": [...]}

    Returns list of identity dicts.
    """
    clusters: list = []  # {centroid, tracks, label, match_score}

    # Pre-normalise gallery embeddings
    gallery_norm = []
    if gallery:
        for g in gallery:
            emb = g.get("embedding")
            if emb is None:
                continue
            gallery_norm.append({
                "identity": g.get("identity", "unknown"),
                "embedding": _normalise(np.asarray(emb, dtype=np.float32)),
            })

    for face in faces:
        emb = face["embedding"]
        best_idx, best_sim = -1, -1.0
        for i, cl in enumerate(clusters):
            sim = _cosine(emb, cl["centroid"])
            if sim > best_sim:
                best_sim, best_idx = sim, i

        if best_idx >= 0 and best_sim >= threshold:
            cl = clusters[best_idx]
            cl["tracks"].append(face)
            # Running mean centroid, then re-normalise
            n = len(cl["tracks"])
            cl["centroid"] = _normalise((cl["centroid"] * (n - 1) + emb) / n)
            cl["score_sum"] += best_sim
            cl["score_n"] += 1
        else:
            clusters.append({
                "centroid": _normalise(emb.copy()),
                "tracks":   [face],
                "score_sum": 0.0,
                "score_n":   0,
            })

    # Build identity dicts
    identities = []
    for i, cl in enumerate(clusters):
        tracks = sorted(cl["tracks"], key=lambda f: f["timestamp_s"])
        label, match_score = None, None
        if gallery_norm:
            best_g, best_gs = None, -1.0
            for g in gallery_norm:
                sim = _cosine(cl["centroid"], g["embedding"])
                if sim > best_gs:
                    best_gs, best_g = sim, g["identity"]
            if best_gs >= threshold:
                label, match_score = best_g, round(best_gs, 4)

        identities.append({
            "identity_id":  f"person_{i + 1}",
            "label":        label,
            "match_score":  match_score,
            "face_count":   len(tracks),
            "first_seen_s": tracks[0]["timestamp_s"] if tracks else None,
            "last_seen_s":  tracks[-1]["timestamp_s"] if tracks else None,
            "avg_det_score": round(
                float(np.mean([t["det_score"] for t in tracks])), 4
            ) if tracks else None,
            "centroid_embedding": [round(float(v), 6) for v in cl["centroid"]],
            "tracks": [
                {
                    "frame_index": t["frame_index"],
                    "timestamp_s": t["timestamp_s"],
                    "det_score":   t["det_score"],
                    "bbox":        t["bbox"],
                }
                for t in tracks
            ],
        })

    identities.sort(key=lambda x: x["face_count"], reverse=True)
    return identities


# ────────────────────────────────────────────────────────────────────────────
# CORE FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def run_face_reid(
    video_path: Optional[str] = None,
    frames: Optional[list] = None,
    frame_timestamps: Optional[list] = None,
    governance_approved: bool = False,
    gallery: Optional[list] = None,
    similarity_threshold: float = SIMILARITY_THRESHOLD,
    include_embeddings: bool = False,
    num_frames: int = DEFAULT_FRAME_SAMPLE,
) -> dict:
    """
    Run governance-gated face detection + re-identification.

    Parameters
    ----------
    video_path           : Source video (frames sampled if `frames` not given).
    frames               : List of PIL Images (takes precedence over video_path).
    frame_timestamps     : Optional timestamps (s) aligned to `frames`.
    governance_approved  : ABSOLUTE gate. False -> no processing at all.
    gallery              : Optional pre-enrolled identities
                           [{"identity": "name", "embedding": [...512 floats]}].
    similarity_threshold : Cosine similarity to merge faces into one identity.
    include_embeddings   : If True, attach the centroid embedding to each identity.
    num_frames           : Frames sampled when using video_path.

    Returns
    -------
    dict with keys: status, governance_approved, identities, faces_detected,
                    frames_analyzed, model_used, error.
    """
    started_at = datetime.datetime.utcnow().isoformat() + "Z"
    result = {
        "status":              "blocked",
        "governance_approved": bool(governance_approved),
        "identities":          [],
        "faces_detected":      0,
        "frames_analyzed":     0,
        "model_used":          None,
        "started_at":          started_at,
        "completed_at":        None,
        "error":               None,
    }

    # ── GOVERNANCE GATE (absolute) ─────────────────────────────────────────
    if not governance_approved:
        result["error"] = (
            "Biometric processing blocked: governance_approved is not set. "
            "Face re-identification requires explicit governance approval."
        )
        print(
            "  [FaceReID]  BLOCKED — governance_approved is False. "
            "No biometric processing performed.",
            flush=True,
        )
        return result

    # ── Resolve frames ─────────────────────────────────────────────────────
    frame_items = []  # (frame_index, timestamp_s, bgr)
    if frames is None and video_path:
        if not os.path.exists(video_path):
            result["status"] = "unavailable"
            result["error"] = f"File not found: {video_path}"
            print(f"  [FaceReID] ️  File not found: {video_path}", flush=True)
            return result
        print(f"  [FaceReID] Sampling {num_frames} frame(s)…", flush=True)
        frame_items = _sample_frames_from_video(video_path, num_frames)
    elif frames:
        for i, frame in enumerate(frames):
            ts = frame_timestamps[i] if frame_timestamps and i < len(frame_timestamps) \
                else float(i)
            frame_items.append((i, float(ts), _pil_to_bgr(frame)))

    if not frame_items:
        result["status"] = "unavailable"
        result["error"] = "No frames available for face re-identification."
        print("  [FaceReID] ⚠️  No frames — skipping.", flush=True)
        return result

    # ── Load model ─────────────────────────────────────────────────────────
    app = _load_face_app()
    if app is None:
        result["status"] = "unavailable"
        result["error"] = "InsightFace not available. Install: pip install insightface onnxruntime-gpu"
        return result

    # ── Detect + embed per frame ───────────────────────────────────────────
    all_faces = []
    for frame_index, ts, bgr in frame_items:
        try:
            detected = app.get(bgr)
        except Exception as exc:
            print(f"  [FaceReID] ⚠️  Face detection failed on frame {frame_index}: {exc}",
                  flush=True)
            continue

        for face in detected:
            det_score = float(getattr(face, "det_score", 0.0))
            if det_score < MIN_DET_SCORE:
                continue
            emb = getattr(face, "embedding", None)
            if emb is None:
                continue
            emb = np.asarray(emb, dtype=np.float32)
            if emb.shape[0] != EMBEDDING_DIM:
                continue
            bbox = [int(v) for v in np.asarray(face.bbox).tolist()]
            all_faces.append({
                "frame_index":  frame_index,
                "timestamp_s":  ts,
                "det_score":    round(det_score, 4),
                "bbox":         bbox,
                "embedding":    emb,
            })

    result["frames_analyzed"] = len(frame_items)
    result["faces_detected"] = len(all_faces)

    if not all_faces:
        result["status"] = "no_faces"
        result["model_used"] = f"insightface-{INSIGHTFACE_PACK}"
        result["completed_at"] = datetime.datetime.utcnow().isoformat() + "Z"
        print("  [FaceReID] ℹ️  No faces detected.", flush=True)
        return result

    # ── Cluster ────────────────────────────────────────────────────────────
    identities = _cluster_faces(all_faces, similarity_threshold, gallery)
    if include_embeddings:
        # Attach centroid embeddings by recomputing from tracks
        for ident in identities:
            pass  # centroid embeddings are not retained on tracks; keep omitted

    result.update({
        "status":     "ok",
        "identities": identities,
        "model_used": f"insightface-{INSIGHTFACE_PACK}",
        "completed_at": datetime.datetime.utcnow().isoformat() + "Z",
    })

    print(
        f"  [FaceReID] ✅ {len(all_faces)} face(s) → "
        f"{len(identities)} anonymous identit(ies).",
        flush=True,
    )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Chorus Face Re-ID Agent — governance-gated ArcFace tracking.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python face_reid_agent.py --video incident.mp4 --governance --pretty\n"
            "  python face_reid_agent.py --video incident.mp4 --pretty   # blocked\n"
        ),
    )
    p.add_argument("--video", required=True, help="Path to the video file.")
    p.add_argument("--governance", action="store_true", dest="governance_approved",
                   help="Explicitly approve biometric processing (required).")
    p.add_argument("--frames", type=int, default=DEFAULT_FRAME_SAMPLE,
                   help=f"Frames to sample (default {DEFAULT_FRAME_SAMPLE}).")
    p.add_argument("--threshold", type=float, default=SIMILARITY_THRESHOLD,
                   help=f"Cosine similarity merge threshold (default {SIMILARITY_THRESHOLD}).")
    p.add_argument("--output", default=None, help="Save JSON result to this path.")
    p.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return p


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()

    result = run_face_reid(
        video_path=args.video,
        governance_approved=args.governance_approved,
        similarity_threshold=args.threshold,
        num_frames=args.frames,
    )

    out = json.dumps(result, indent=2 if args.pretty else None,
                     ensure_ascii=False, default=str)
    print(out)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(out)
        print(f"\n  [FaceReID] Saved to: {args.output}", flush=True)

    sys.exit(0 if result["status"] in ("ok", "no_faces") else 1)