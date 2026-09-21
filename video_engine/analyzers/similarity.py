"""
video_engine/analyzers/similarity.py
======================================
Perceptual similarity and near-duplicate detection.

Methods
-------
1. cv2.img_hash.PHash  — perceptual hash (requires opencv-contrib-python).
   Hamming distance < 10 → near-duplicate.
2. ORB feature keypoint density — lightweight frame signature,
   useful for detecting visually repetitive segments.

compare_videos(video_path_a, video_path_b) — runs two engines and
computes a similarity report between the two VideoProfiles.
"""

import cv2
import numpy as np
import logging
from .base import BaseAnalyzer

log = logging.getLogger("chorus.video_engine.similarity")

_SAMPLE_EVERY_N = 15        # how often to hash (every 15 sampled frames)
_DUP_HAMMING_THRESHOLD = 10 # PHash distance below this = near-duplicate


class SimilarityAnalyzer(BaseAnalyzer):
    name = "SimilarityAnalyzer"

    @classmethod
    def is_available(cls) -> bool:
        return hasattr(cv2, "img_hash")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._phash_ok = hasattr(cv2, "img_hash")
        if self._phash_ok:
            self._hasher = cv2.img_hash.PHash_create()
        else:
            log.warning(
                "SimilarityAnalyzer: cv2.img_hash not available; "
                "install opencv-contrib-python to enable PHash."
            )
        self._orb = cv2.ORB_create(nfeatures=100)

        self._hashes: list = []      # [{ts, hex}]
        self._kp_counts: list = []   # [{ts, count}]
        self._near_dups: list = []   # [{ts_a, ts_b, hamming}]

    def on_frame(self, frame: np.ndarray, ts: float, frame_idx: int):
        if frame_idx % _SAMPLE_EVERY_N != 0:
            return

        # ── ORB keypoint count ─────────────────────────────────────────────
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        kp = self._orb.detect(gray, None)
        self._kp_counts.append({"ts": round(ts, 3), "count": len(kp)})

        # ── PHash ─────────────────────────────────────────────────────────
        if not self._phash_ok:
            return

        try:
            h = self._hasher.compute(frame)
            hex_hash = h.tobytes().hex()
            # Near-dup: compare with last hash
            if self._hashes:
                prev_h_bytes = bytes.fromhex(self._hashes[-1]["hex"])
                prev_h = np.frombuffer(prev_h_bytes, dtype=np.uint8).reshape(1, -1)
                curr_h = h.reshape(1, -1)
                dist = int(self._hasher.compare(prev_h, curr_h))
                if dist < _DUP_HAMMING_THRESHOLD:
                    self._near_dups.append({
                        "ts_a": self._hashes[-1]["ts"],
                        "ts_b": round(ts, 3),
                        "hamming": dist,
                    })
            self._hashes.append({"ts": round(ts, 3), "hex": hex_hash})
        except Exception as exc:
            log.debug("PHash compute failed: %s", exc)

    def finalize(self) -> dict:
        if not self._phash_ok:
            return {
                "status": "unavailable",
                "reason": "cv2.img_hash requires opencv-contrib-python.",
                "orb_kp_counts": self._kp_counts[:200],
            }
        return {
            "status": "ok",
            "hash_count": len(self._hashes),
            "near_duplicate_segments": self._near_dups[:100],
            "orb_kp_counts": self._kp_counts[:200],
            "parameters": {
                "sample_every_n": _SAMPLE_EVERY_N,
                "dup_hamming_threshold": _DUP_HAMMING_THRESHOLD,
            },
            "limitations": (
                "PHash compares consecutive sampled frames only. "
                "Cross-clip comparison requires calling compare_videos()."
            ),
        }


def compare_videos(path_a: str, path_b: str, sample_fps: float = 1.0) -> dict:
    """
    Run lightweight similarity analysis on two video paths.
    Returns a comparison dict (NOT RUN — requires engine invocation).

    This function is NOT called by the normal pipeline; it is intended
    for the Trace page / 'compare two uploads' flow.
    """
    from ..reader import VideoReader
    hashes_a: list = []
    hashes_b: list = []

    phash_ok = hasattr(cv2, "img_hash")
    if not phash_ok:
        return {"status": "unavailable", "reason": "cv2.img_hash not available"}

    hasher = cv2.img_hash.PHash_create()

    def _collect(path: str, target: list):
        try:
            r = VideoReader(path)
            for idx, ts, frame in r.iter_frames(sample_rate_fps=sample_fps):
                h = hasher.compute(frame)
                target.append(h.tobytes())
            r.release()
        except Exception as exc:
            log.warning("compare_videos: cannot read %s: %s", path, exc)

    _collect(path_a, hashes_a)
    _collect(path_b, hashes_b)

    if not hashes_a or not hashes_b:
        return {"status": "error", "reason": "Could not read one or both videos"}

    # Compute a coarse average distance between the two sets
    n = min(len(hashes_a), len(hashes_b))
    total_dist = 0
    for i in range(n):
        h1 = np.frombuffer(hashes_a[i], dtype=np.uint8).reshape(1, -1)
        h2 = np.frombuffer(hashes_b[i], dtype=np.uint8).reshape(1, -1)
        total_dist += int(hasher.compare(h1, h2))
    avg_dist = total_dist / n if n > 0 else 999

    return {
        "status": "ok",
        "path_a": path_a,
        "path_b": path_b,
        "frames_compared": n,
        "avg_phash_distance": round(avg_dist, 2),
        "likely_duplicate": avg_dist < _DUP_HAMMING_THRESHOLD,
        "similarity_score": round(max(0.0, 1.0 - avg_dist / 64.0), 4),
    }
