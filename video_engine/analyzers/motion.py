"""
video_engine/analyzers/motion.py
=================================
Motion and activity analyzer.

Outputs
-------
- activity_timeline: [(ts, activity_level_0_to_1), ...]
  activity_level = fraction of foreground pixels from MOG2
- motion_peaks: timestamps where activity > peak_threshold
- camera_motion: [(ts, dx, dy, type_hint), ...]
  from sparse optical flow + homography (ORB features)
- avg_activity: float 0-1
- heatmap: JSON-serializable base64-encoded PNG (if compute_heatmap=True)

Limitations
-----------
- MOG2 needs warm-up (~50 frames); early frames may show high activity.
- Camera motion via homography only reliable when >= 4 ORB matches.
- Heatmap accumulates motion over entire clip (not per scene).
"""

import cv2
import numpy as np
import base64
import logging
from .base import BaseAnalyzer

log = logging.getLogger("chorus.video_engine.motion")


class MotionAnalyzer(BaseAnalyzer):
    name = "MotionAnalyzer"

    def __init__(
        self,
        compute_heatmap: bool = True,
        peak_threshold: float = 0.08,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.compute_heatmap = compute_heatmap
        self.peak_threshold = peak_threshold

        self._mog2 = cv2.createBackgroundSubtractorMOG2(
            history=500, varThreshold=16, detectShadows=False
        )
        self._prev_gray: np.ndarray = None
        self._prev_pts = None
        self._heatmap: np.ndarray = None
        self._h: int = 0
        self._w: int = 0

        self._activity: list = []      # [(ts, level)]
        self._camera_motion: list = [] # [(ts, dx, dy, hint)]
        self._frame_count: int = 0
        self._orb = cv2.ORB_create(nfeatures=300)

    def on_frame(self, frame: np.ndarray, ts: float, frame_idx: int):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        self._h, self._w = h, w
        self._frame_count += 1

        # ── 1. MOG2 foreground mask → activity level ──────────────────────
        fg = self._mog2.apply(frame)
        # threshold: keep hard foreground (>128), drop shadows
        _, fg_binary = cv2.threshold(fg, 200, 255, cv2.THRESH_BINARY)
        level = float(np.count_nonzero(fg_binary)) / (h * w)
        self._activity.append((round(ts, 3), round(level, 5)))

        # ── 2. Optical flow + heatmap + camera motion ─────────────────────
        if self._prev_gray is not None:
            # Sparse LK flow on good features
            if self._prev_pts is None or len(self._prev_pts) < 30:
                self._prev_pts = cv2.goodFeaturesToTrack(
                    self._prev_gray, maxCorners=300, qualityLevel=0.01, minDistance=8
                )

            if self._prev_pts is not None and len(self._prev_pts) > 0:
                curr_pts, status, _ = cv2.calcOpticalFlowPyrLK(
                    self._prev_gray, gray, self._prev_pts, None,
                    winSize=(15, 15), maxLevel=3,
                    criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03),
                )
                good_new = curr_pts[status == 1]
                good_old = self._prev_pts[status == 1]

                # Heatmap accumulation
                if self.compute_heatmap:
                    if self._heatmap is None:
                        self._heatmap = np.zeros((h, w), dtype=np.float32)
                    for n, o in zip(good_new, good_old):
                        nx, ny = n.ravel()
                        ox, oy = o.ravel()
                        dist = float(np.hypot(nx - ox, ny - oy))
                        if 0 <= int(ny) < h and 0 <= int(nx) < w:
                            cv2.circle(self._heatmap, (int(nx), int(ny)),
                                       max(2, int(dist / 3 + 2)), dist, -1)

                # Camera motion via homography (every 5 frames for speed)
                if frame_idx % 5 == 0 and len(good_new) >= 4:
                    H, inliers = cv2.findHomography(good_old, good_new, cv2.RANSAC, 3.0)
                    if H is not None:
                        dx = float(H[0, 2])
                        dy = float(H[1, 2])
                        scale = float(np.sqrt(H[0, 0] ** 2 + H[1, 0] ** 2))
                        hint = "pan" if abs(dx) > 3 or abs(dy) > 3 else \
                               ("zoom" if abs(scale - 1.0) > 0.05 else "stable")
                        self._camera_motion.append(
                            (round(ts, 3), round(dx, 2), round(dy, 2), hint)
                        )

                self._prev_pts = good_new.reshape(-1, 1, 2) if len(good_new) > 0 else None

        self._prev_gray = gray

    def _heatmap_b64(self) -> str:
        """Return base64-encoded PNG of the motion heatmap, or ''."""
        if self._heatmap is None or self._heatmap.max() == 0:
            return ""
        try:
            norm = cv2.normalize(self._heatmap, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
            colored = cv2.applyColorMap(norm, cv2.COLORMAP_JET)
            _, buf = cv2.imencode(".png", colored)
            return base64.b64encode(buf.tobytes()).decode("ascii")
        except Exception as exc:
            log.warning("Heatmap encoding failed: %s", exc)
            return ""

    def finalize(self) -> dict:
        peaks = [ts for ts, lvl in self._activity if lvl > self.peak_threshold]
        avg = round(sum(l for _, l in self._activity) / len(self._activity), 5) \
            if self._activity else 0.0

        return {
            "status": "ok",
            "frame_count": self._frame_count,
            "avg_activity": avg,
            "activity_timeline": self._activity[::3],  # thin for JSON size
            "peaks": peaks[:100],
            "camera_motion": self._camera_motion[:200],
            "heatmap_png_b64": self._heatmap_b64() if self.compute_heatmap else "",
            "parameters": {
                "peak_threshold": self.peak_threshold,
                "compute_heatmap": self.compute_heatmap,
            },
            "limitations": (
                "MOG2 warm-up ~50 frames; early activity levels inflated. "
                "Camera motion only reliable with >= 4 tracked points."
            ),
        }
