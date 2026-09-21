"""
video_engine/analyzers/shots.py
================================
Shot / scene-cut detector and keyframe extractor.

Uses PySceneDetect ContentDetector (general) or AdaptiveDetector (cyber).
Falls back to a pure-OpenCV histogram diff detector when scenedetect is
not installed — the run continues with a degraded note in the result.

Keyframes: the first frame after each cut is stored (memory-bounded:
max 50 frames kept as JPEG bytes).
"""

import cv2
import numpy as np
import base64
import logging
from .base import BaseAnalyzer

log = logging.getLogger("chorus.video_engine.shots")

try:
    from scenedetect.detectors import ContentDetector, AdaptiveDetector
    _PYSCENE_OK = True
except ImportError:
    _PYSCENE_OK = False
    ContentDetector = None
    AdaptiveDetector = None

_MAX_KEYFRAMES = 50
_JPEG_QUALITY = 75


def _frame_to_b64(frame: np.ndarray) -> str:
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, _JPEG_QUALITY])
    return base64.b64encode(buf.tobytes()).decode("ascii")


class _HistogramCutDetector:
    """Fallback: simple histogram-difference shot detector."""
    def __init__(self, threshold: float = 0.45):
        self.threshold = threshold
        self._prev_hist = None
        self.cuts: list = []

    def process_frame(self, frame_idx: int, frame: np.ndarray) -> list:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        hist = cv2.calcHist([gray], [0], None, [64], [0, 256])
        hist = cv2.normalize(hist, hist).flatten()

        cuts = []
        if self._prev_hist is not None:
            diff = float(cv2.compareHist(self._prev_hist, hist, cv2.HISTCMP_BHATTACHARYYA))
            if diff > self.threshold:
                cuts.append(frame_idx)
        self._prev_hist = hist
        return cuts

    def post_process(self, _):
        pass


class ShotsAnalyzer(BaseAnalyzer):
    name = "ShotsAnalyzer"

    @classmethod
    def is_available(cls) -> bool:
        return True  # always available (histogram fallback)

    def __init__(self, mode: str = "general", **kwargs):
        super().__init__(**kwargs)
        self.mode = mode
        self._using_pyscene = False

        if _PYSCENE_OK:
            self._detector = (AdaptiveDetector() if mode == "cyber"
                              else ContentDetector(threshold=27.0))
            self._using_pyscene = True
        else:
            self._detector = _HistogramCutDetector(threshold=0.25)
            log.warning("ShotsAnalyzer: scenedetect not installed, using histogram fallback")

        self._cuts: list = []       # [(ts, frame_idx)]
        self._keyframes: list = []  # [{ts, frame_idx, image_b64}]
        self._last_ts: float = 0.0
        self._total_frames: int = 0

    def on_frame(self, frame: np.ndarray, ts: float, frame_idx: int):
        self._last_ts = ts
        self._total_frames = frame_idx + 1

        try:
            cuts_found = self._detector.process_frame(frame_idx, frame)
        except Exception as exc:
            log.debug("ShotsAnalyzer detector error at frame %d: %s", frame_idx, exc)
            return

        for cut_frame in (cuts_found or []):
            self._cuts.append((round(ts, 3), int(cut_frame)))
            # Store keyframe
            if len(self._keyframes) < _MAX_KEYFRAMES:
                try:
                    self._keyframes.append({
                        "ts": round(ts, 3),
                        "frame_idx": frame_idx,
                        "image_b64": _frame_to_b64(frame),
                    })
                except Exception:
                    pass

    def finalize(self) -> dict:
        try:
            self._detector.post_process(-1)
        except Exception:
            pass

        # Build scene list from cuts
        scenes = []
        prev_ts = 0.0
        for ts, _ in sorted(self._cuts):
            scenes.append({
                "start_seconds": round(prev_ts, 3),
                "end_seconds": round(ts, 3),
                "duration": round(ts - prev_ts, 3),
            })
            prev_ts = ts
        # Final scene
        if self._last_ts > prev_ts:
            scenes.append({
                "start_seconds": round(prev_ts, 3),
                "end_seconds": round(self._last_ts, 3),
                "duration": round(self._last_ts - prev_ts, 3),
            })

        # Keyframe list without raw bytes (too large for most transports)
        kf_meta = [{"ts": k["ts"], "frame_idx": k["frame_idx"]} for k in self._keyframes]

        return {
            "status": "ok",
            "detector": "pyscenedetect" if self._using_pyscene else "histogram_fallback",
            "mode": self.mode,
            "cut_count": len(self._cuts),
            "cuts": [{"ts": t, "frame_idx": fi} for t, fi in self._cuts],
            "scenes": scenes,
            "scene_count": len(scenes),
            "keyframe_timestamps": [k["ts"] for k in self._keyframes],
            "keyframes_meta": kf_meta,
            # Keyframe images available separately to keep JSON light
            "_keyframes_images": self._keyframes,  # internal, not serialized to profile
            "limitations": (
                "PySceneDetect used." if self._using_pyscene
                else "scenedetect not installed; histogram fallback used (less accurate)."
            ),
        }
