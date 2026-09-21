"""
video_engine/analyzers/export.py
==================================
Annotated video export, thumbnails, contact sheet.

Uses cv2.VideoWriter for the annotated video (no audio).
Audio is muxed back via a final ffmpeg subprocess call (audio-preserving).

Rules
-----
- Does NOT accumulate frames in memory; writes to disk immediately.
- Writes to output_dir / annotated_raw.mp4 (video only).
- Final step: ffmpeg mux audio from original into annotated.mp4.
- Thumbnails are written every thumb_every_n frames (default: every 100).
- Contact sheet: a grid of all thumbnails.
"""

import cv2
import numpy as np
import os
import subprocess
import logging
from typing import Optional
from .base import BaseAnalyzer

log = logging.getLogger("chorus.video_engine.export")


class ExportAnalyzer(BaseAnalyzer):
    name = "ExportAnalyzer"

    def __init__(
        self,
        output_dir: str,
        original_path: str = "",
        fps: float = 25.0,
        thumb_every_n: int = 100,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.output_dir = output_dir
        self.original_path = original_path
        self.fps = fps
        self.thumb_every_n = thumb_every_n

        os.makedirs(self.output_dir, exist_ok=True)
        self._writer: Optional[cv2.VideoWriter] = None
        self._raw_path = os.path.join(self.output_dir, "annotated_raw.mp4")
        self._final_path = os.path.join(self.output_dir, "annotated.mp4")
        self._thumbs: list = []
        self._error: Optional[str] = None

    def on_frame(self, frame: np.ndarray, ts: float, frame_idx: int):
        h, w = frame.shape[:2]

        # Lazy-init writer on first frame
        if self._writer is None:
            try:
                fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                self._writer = cv2.VideoWriter(self._raw_path, fourcc, self.fps, (w, h))
                if not self._writer.isOpened():
                    self._error = f"VideoWriter failed to open {self._raw_path}"
                    self._writer = None
                    return
            except Exception as exc:
                self._error = str(exc)
                return

        # Annotation overlay
        annotated = frame.copy()
        ts_str = f"{int(ts // 60):02d}:{ts % 60:.2f}"
        cv2.rectangle(annotated, (0, 0), (220, 40), (0, 0, 0), -1)
        cv2.putText(annotated, ts_str, (8, 28), cv2.FONT_HERSHEY_SIMPLEX,
                    0.8, (0, 255, 100), 2, cv2.LINE_AA)

        self._writer.write(annotated)

        # Thumbnail
        if frame_idx % self.thumb_every_n == 0:
            thumb_path = os.path.join(self.output_dir, f"thumb_{frame_idx:06d}.jpg")
            cv2.imwrite(thumb_path, cv2.resize(annotated, (320, 180)))
            self._thumbs.append({"frame_idx": frame_idx, "ts": round(ts, 3), "path": thumb_path})

    def finalize(self) -> dict:
        if self._writer:
            self._writer.release()
            self._writer = None

        if self._error:
            return {"status": "error", "reason": self._error}

        # Mux audio with ffmpeg
        audio_ok = False
        if self.original_path and os.path.exists(self.original_path) and os.path.exists(self._raw_path):
            try:
                cmd = [
                    "ffmpeg", "-y",
                    "-i", self._raw_path,
                    "-i", self.original_path,
                    "-c:v", "copy", "-c:a", "aac",
                    "-map", "0:v:0", "-map", "1:a:0?",
                    "-shortest",
                    self._final_path,
                ]
                result = subprocess.run(
                    cmd, stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE, timeout=300
                )
                audio_ok = result.returncode == 0
                if audio_ok:
                    os.remove(self._raw_path)
                else:
                    # Fall back: rename raw as final
                    os.rename(self._raw_path, self._final_path)
                    log.warning("ExportAnalyzer: audio mux failed, using video-only: %s",
                                result.stderr.decode(errors="replace")[-200:])
            except Exception as exc:
                log.warning("ExportAnalyzer: ffmpeg mux exception: %s", exc)
                if os.path.exists(self._raw_path):
                    os.rename(self._raw_path, self._final_path)
        elif os.path.exists(self._raw_path):
            os.rename(self._raw_path, self._final_path)

        # Contact sheet
        contact_sheet_path = self._make_contact_sheet()

        return {
            "status": "ok",
            "annotated_video": self._final_path if os.path.exists(self._final_path) else None,
            "audio_muxed": audio_ok,
            "thumbnails": self._thumbs,
            "contact_sheet": contact_sheet_path,
            "parameters": {
                "fps": self.fps,
                "thumb_every_n": self.thumb_every_n,
            },
        }

    def _make_contact_sheet(self) -> Optional[str]:
        if not self._thumbs:
            return None
        try:
            images = []
            for t in self._thumbs[:48]:  # max 48 thumbs
                img = cv2.imread(t["path"])
                if img is not None:
                    images.append(cv2.resize(img, (320, 180)))
            if not images:
                return None
            cols = 4
            rows = (len(images) + cols - 1) // cols
            ih, iw = images[0].shape[:2]
            sheet = np.zeros((rows * ih, cols * iw, 3), dtype=np.uint8)
            for i, img in enumerate(images):
                r, c = divmod(i, cols)
                sheet[r * ih:(r + 1) * ih, c * iw:(c + 1) * iw] = img
            path = os.path.join(self.output_dir, "contact_sheet.jpg")
            cv2.imwrite(path, sheet, [cv2.IMWRITE_JPEG_QUALITY, 85])
            return path
        except Exception as exc:
            log.warning("ExportAnalyzer: contact sheet failed: %s", exc)
            return None
