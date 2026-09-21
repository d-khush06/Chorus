"""
video_engine/analyzers/faces.py
================================
Face detection and counting using YuNet (cv2.FaceDetectorYN).

NO identification or recognition is performed here.
Governance gates for any recognition remain in the existing pipeline.

Model path: face_detection_yunet_2023mar.onnx
Available from: https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet
"""

import cv2
import numpy as np
import os
import logging
from .base import BaseAnalyzer

log = logging.getLogger("chorus.video_engine.faces")

_DEFAULT_MODEL = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "models", "face_detection_yunet_2023mar.onnx"
)

_DETECT_EVERY_N = 10   # run detection every N frames


class FaceAnalyzer(BaseAnalyzer):
    name = "FaceAnalyzer"

    def __init__(self, model_path: str = _DEFAULT_MODEL, conf_threshold: float = 0.85, **kwargs):
        super().__init__(**kwargs)
        self.model_path = model_path
        self.conf_threshold = conf_threshold
        self._detector = None
        self.available = False
        self._timeline: list = []     # [{ts, count, faces:[{box,conf}]}]
        self._total = 0

        if os.path.exists(self.model_path):
            try:
                self._detector = cv2.FaceDetectorYN.create(
                    self.model_path, "", (320, 320),
                    self.conf_threshold, 0.3, 5000
                )
                self.available = True
                log.info("FaceAnalyzer: YuNet loaded from %s", self.model_path)
            except Exception as exc:
                log.warning("FaceAnalyzer: cannot load YuNet: %s", exc)
        else:
            log.info(
                "FaceAnalyzer: model not found at '%s'. "
                "Download from opencv_zoo to enable face detection.", self.model_path
            )

    def on_frame(self, frame: np.ndarray, ts: float, frame_idx: int):
        if not self.available or frame_idx % _DETECT_EVERY_N != 0:
            return

        h, w = frame.shape[:2]
        self._detector.setInputSize((w, h))

        try:
            retcode, faces = self._detector.detect(frame)
        except Exception as exc:
            log.debug("FaceAnalyzer detect() failed: %s", exc)
            return

        if faces is None or len(faces) == 0:
            return

        count = len(faces)
        self._total += count
        face_list = []
        for face in faces:
            x, y, fw, fh = int(face[0]), int(face[1]), int(face[2]), int(face[3])
            conf = round(float(face[14]), 3) if len(face) > 14 else 0.0
            face_list.append({"box": [x, y, fw, fh], "conf": conf})

        self._timeline.append({"ts": round(ts, 3), "count": count, "faces": face_list})

    def finalize(self) -> dict:
        if not self.available:
            return {
                "status": "unavailable",
                "reason": (
                    f"YuNet model not found at '{self.model_path}'. "
                    "Download face_detection_yunet_2023mar.onnx from opencv_zoo."
                ),
                "model_path": self.model_path,
            }
        return {
            "status": "ok",
            "model_path": self.model_path,
            "total_detected_instances": self._total,
            "timeline": self._timeline[:500],
            "parameters": {
                "conf_threshold": self.conf_threshold,
                "detect_every_n": _DETECT_EVERY_N,
            },
            "limitations": (
                "Detection only — no identification or recognition. "
                "YuNet accurate for frontal/near-frontal faces; profiles may be missed."
            ),
        }
