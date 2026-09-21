"""
video_engine/analyzers/text.py
================================
On-screen text and code detection.

Priority order
--------------
1. cv2.QRCodeDetector  — always available (OpenCV built-in)
2. Tesseract (pytesseract)  — if tesseract binary is on PATH
3. cv2.dnn EAST text detector — if east_text_detection.pb is present
   (download from: https://github.com/oyyd/frozen_east_text_detection.pb)

Each method runs independently. The result merges all findings.

Limitations
-----------
- Tesseract OCR accuracy varies with font size and contrast.
- QR decoder requires the code to be un-obstructed and >~50px.
- EAST detects regions but does not read text; combined with Tesseract it
  can read localised ROIs (not yet implemented here — planned).
"""

import cv2
import numpy as np
import os
import shutil
import logging
from .base import BaseAnalyzer

log = logging.getLogger("chorus.video_engine.text")

_RUN_EVERY_N = 30   # OCR is slow; run every N frames
_EAST_MODEL = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "models", "frozen_east_text_detection.pb"
)


class TextAndCodeAnalyzer(BaseAnalyzer):
    name = "TextAndCodeAnalyzer"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._qr = cv2.QRCodeDetector()

        # Tesseract
        self._tesseract_ok = False
        self._pytesseract = None
        if shutil.which("tesseract"):
            try:
                import pytesseract
                self._pytesseract = pytesseract
                self._tesseract_ok = True
                log.info("TextAndCodeAnalyzer: Tesseract available")
            except ImportError:
                log.info("TextAndCodeAnalyzer: pytesseract not installed")
        else:
            log.info("TextAndCodeAnalyzer: tesseract binary not on PATH")

        # EAST text detector
        self._east_net = None
        if os.path.exists(_EAST_MODEL):
            try:
                self._east_net = cv2.dnn.readNet(_EAST_MODEL)
                log.info("TextAndCodeAnalyzer: EAST detector loaded from %s", _EAST_MODEL)
            except Exception as exc:
                log.warning("TextAndCodeAnalyzer: EAST load failed: %s", exc)

        self._codes: list = []
        self._texts: list = []
        self._east_regions: list = []

    def on_frame(self, frame: np.ndarray, ts: float, frame_idx: int):
        if frame_idx % _RUN_EVERY_N != 0:
            return

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # ── 1. QR / barcodes ─────────────────────────────────────────────────
        try:
            ok, decoded_info, pts, _ = self._qr.detectAndDecodeMulti(gray)
            if ok and decoded_info:
                for info in decoded_info:
                    if info:
                        self._codes.append({"ts": round(ts, 3), "type": "QR", "data": info})
        except Exception:
            # Older OpenCV: single QR
            try:
                data, pts, _ = self._qr.detectAndDecode(gray)
                if data:
                    self._codes.append({"ts": round(ts, 3), "type": "QR", "data": data})
            except Exception:
                pass

        # ── 2. Tesseract OCR ──────────────────────────────────────────────────
        if self._tesseract_ok:
            try:
                text = self._pytesseract.image_to_string(
                    gray, config="--psm 6 --oem 1"
                ).strip()
                if text and len(text) > 3:
                    self._texts.append({"ts": round(ts, 3), "text": text[:500]})
            except Exception as exc:
                log.debug("Tesseract error at ts=%.2f: %s", ts, exc)

        # ── 3. EAST text-region detection ─────────────────────────────────────
        if self._east_net is not None:
            try:
                blob = cv2.dnn.blobFromImage(
                    cv2.resize(frame, (320, 320)),
                    1.0, (320, 320), (123.68, 116.78, 103.94),
                    swapRB=True, crop=False,
                )
                self._east_net.setInput(blob)
                scores, geometry = self._east_net.forward(
                    ["feature_fusion/Conv_7/Sigmoid", "feature_fusion/concat_3"]
                )
                # Count non-background text regions
                h_score = scores.shape[2]
                w_score = scores.shape[3]
                strong = int(np.sum(scores[0, 0] > 0.5))
                if strong > 0:
                    self._east_regions.append({
                        "ts": round(ts, 3),
                        "text_regions_detected": strong,
                    })
            except Exception as exc:
                log.debug("EAST error at ts=%.2f: %s", ts, exc)

    def finalize(self) -> dict:
        available_backends = ["QRCodeDetector (built-in)"]
        if self._tesseract_ok:
            available_backends.append("Tesseract OCR")
        else:
            available_backends.append("Tesseract: UNAVAILABLE (not on PATH)")
        if self._east_net is not None:
            available_backends.append("EAST text detector")
        else:
            available_backends.append(f"EAST: UNAVAILABLE (model not found at {_EAST_MODEL})")

        return {
            "status": "ok",
            "detected_codes": self._codes[:200],
            "detected_texts": self._texts[:200],
            "east_text_regions": self._east_regions[:100],
            "backends": available_backends,
            "text_detection_available": self._tesseract_ok or self._east_net is not None,
            "parameters": {
                "run_every_n": _RUN_EVERY_N,
            },
            "limitations": (
                "Tesseract accuracy degrades on stylised fonts, low contrast, or small text. "
                "EAST only detects regions (no OCR). QR requires >~50px and clear view."
            ),
        }
