"""
video_engine/analyzers/technical.py
====================================
Technical quality analyzer.

Metrics
-------
- Blur: Laplacian variance (lower = blurrier)
- Exposure: mean pixel brightness of grayscale frame
- Contrast: std-dev of pixel brightness
- Black frames: mean < black_threshold AND stddev < black_threshold
- Frozen frames: mean absolute diff from previous frame < frozen_threshold
- Letterbox / pillarbox: detect uniform black bands
- Noise estimate: mean absolute diff from median-blurred version (every 10 frames)
"""

import cv2
import numpy as np
from .base import BaseAnalyzer


class TechnicalAnalyzer(BaseAnalyzer):
    name = "TechnicalAnalyzer"

    def __init__(
        self,
        black_threshold: float = 5.0,
        frozen_threshold: float = 1.5,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.black_threshold = black_threshold
        self.frozen_threshold = frozen_threshold

        self._blur_scores: list = []
        self._exposure: list = []
        self._contrast: list = []
        self._black_frames: list = []
        self._frozen_frames: list = []
        self._noise: list = []
        self._letterbox: list = []
        self._prev_gray: np.ndarray = None
        self._frame_count = 0

    def on_frame(self, frame: np.ndarray, ts: float, frame_idx: int):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        self._frame_count += 1

        # Blur (Laplacian variance)
        lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        self._blur_scores.append((round(ts, 3), round(lap_var, 2)))

        # Exposure & contrast
        mean, std = cv2.meanStdDev(gray)
        mean_val = float(mean[0][0])
        std_val = float(std[0][0])
        self._exposure.append((round(ts, 3), round(mean_val, 2)))
        self._contrast.append((round(ts, 3), round(std_val, 2)))

        # Black frame
        if mean_val < self.black_threshold and std_val < self.black_threshold:
            self._black_frames.append(round(ts, 3))

        # Frozen frame
        if self._prev_gray is not None:
            diff_mean = float(cv2.mean(cv2.absdiff(gray, self._prev_gray))[0])
            if diff_mean < self.frozen_threshold:
                self._frozen_frames.append(round(ts, 3))

        # Noise (every 10 frames, slightly cheaper)
        if frame_idx % 10 == 0:
            med = cv2.medianBlur(gray, 3)
            noise = float(cv2.mean(cv2.absdiff(gray, med))[0])
            self._noise.append((round(ts, 3), round(noise, 3)))

        # Letterbox / pillarbox detection (every 30 frames)
        if frame_idx % 30 == 0:
            lb = self._detect_letterbox(gray)
            if lb:
                self._letterbox.append((round(ts, 3), lb))

        self._prev_gray = gray

    @staticmethod
    def _detect_letterbox(gray: np.ndarray, band_pct: float = 0.05, threshold: float = 8.0) -> dict:
        """Return letterbox/pillarbox info or empty dict."""
        h, w = gray.shape
        band_h = max(1, int(h * band_pct))
        band_w = max(1, int(w * band_pct))
        top = float(gray[:band_h, :].mean())
        bot = float(gray[-band_h:, :].mean())
        left = float(gray[:, :band_w].mean())
        right = float(gray[:, -band_w:].mean())

        result = {}
        if top < threshold and bot < threshold:
            result["type"] = "letterbox"
        elif left < threshold and right < threshold:
            result["type"] = "pillarbox"
        return result

    def finalize(self) -> dict:
        def _avg(lst):
            return round(sum(v for _, v in lst) / len(lst), 4) if lst else 0.0

        return {
            "status": "ok",
            "frame_count": self._frame_count,
            "avg_blur": _avg(self._blur_scores),
            "avg_exposure": _avg(self._exposure),
            "avg_contrast": _avg(self._contrast),
            "avg_noise": _avg(self._noise),
            "black_frame_count": len(self._black_frames),
            "black_frame_timestamps": self._black_frames[:50],
            "frozen_frame_count": len(self._frozen_frames),
            "frozen_frame_timestamps": self._frozen_frames[:50],
            "letterbox_detections": self._letterbox[:10],
            "blur_timeline": self._blur_scores[::5],       # every 5th sample
            "exposure_timeline": self._exposure[::5],
            "parameters": {
                "black_threshold": self.black_threshold,
                "frozen_threshold": self.frozen_threshold,
            },
            "limitations": "Blur/noise are approximate single-pass estimates; no scene-aware averaging.",
        }
