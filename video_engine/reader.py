"""
video_engine/reader.py
======================
Robust sequential frame reader.

Design contract
---------------
- Single sequential decode pass; never seeks.
- Timestamps from CAP_PROP_POS_MSEC; falls back to sequential counting when PTS == 0.
- Rotation metadata read via ffprobe and applied before yielding.
- Fallback: if OpenCV cannot open the file (HEVC, odd codec, truncated tail)
  an ffmpeg transcode to H.264/mp4 is done once, transparently.
- RTSP / live streams (rtsp://, http://) are opened directly via OpenCV;
  sampling keeps memory bounded.
- 4K + hours-long: frames are never accumulated; caller iterates lazily.
"""

import os
import cv2
import json
import subprocess
import time
import threading
import logging
from typing import Iterator, Tuple, Optional, Dict, Any

log = logging.getLogger("chorus.video_engine.reader")


def _ffprobe_rotation(path: str) -> int:
    """Return the display rotation in degrees (0, 90, 180, 270) via ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_streams", path
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=15)
        data = json.loads(out)
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                # Try side_data tags first (common in mobile video)
                for sd in stream.get("side_data_list", []):
                    rot = sd.get("rotation")
                    if rot is not None:
                        return int(rot) % 360
                # Try tags
                tags = stream.get("tags", {})
                rot = tags.get("rotate", tags.get("rotation"))
                if rot is not None:
                    return int(rot) % 360
    except (FileNotFoundError, Exception):
        pass
    return 0


def _rotate_frame(frame, rotation: int):
    """Apply a clockwise rotation to a frame."""
    if rotation == 90:
        return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    elif rotation == 180:
        return cv2.rotate(frame, cv2.ROTATE_180)
    elif rotation == 270:
        return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return frame


def _is_live(path: str) -> bool:
    return path.lower().startswith(("rtsp://", "rtsps://", "rtmp://", "http://", "https://")) and \
           not path.lower().endswith((".mp4", ".mkv", ".avi", ".mov", ".ts", ".mts", ".m4v"))


class VideoReader:
    """
    Robust sequential video reader.

    Parameters
    ----------
    path        : local file path, RTSP URL, or HTTP stream URL.
    max_retries : number of ffmpeg transcode retries if cv2 fails.

    Attributes
    ----------
    fps, width, height, total_frames, codec_str, rotation, is_live
    """

    def __init__(self, path: str, max_retries: int = 1):
        # Auto-map Wowza Cloud RTSP ingest entrypoints to direct native HLS playback
        if "cloud.wowza.com" in path and (path.startswith("rtsp://") or path.startswith("rtsps://")):
            try:
                from urllib.parse import urlparse
                u = urlparse(path)
                path = f"http://{u.netloc}{u.path}{'' if u.path.endswith('.m3u8') else '/playlist.m3u8'}"
            except Exception:
                pass

        self.path = path
        self.is_live = _is_live(path)
        self._transcoded_path: Optional[str] = None
        self._cancel = threading.Event()

        # Open capture
        self.cap = self._open(path)
        self._fallback_used = False

        if (not self.cap.isOpened() or
                int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)) == 0) and \
                not self.is_live and max_retries > 0:
            self._fallback_used = True
            self.cap.release()
            self.cap = self._transcode_and_open(path)

        if not self.cap.isOpened():
            raise RuntimeError(f"VideoReader: cannot open '{path}'")

        self.fps: float = self.cap.get(cv2.CAP_PROP_FPS) or 25.0
        self.width: int = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height: int = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.total_frames: int = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fourcc_int = int(self.cap.get(cv2.CAP_PROP_FOURCC))
        self.codec_str: str = "".join(chr((fourcc_int >> (i * 8)) & 0xFF) for i in range(4)).strip("\x00")

        # Rotation from ffprobe (0 for streams – we skip that lookup)
        self.rotation: int = 0 if self.is_live else _ffprobe_rotation(self._transcoded_path or path)

        # After rotation, swap w/h if 90 or 270
        if self.rotation in (90, 270):
            self.width, self.height = self.height, self.width

        log.info(
            "VideoReader opened: %s  %dx%d @ %.2f fps  codec=%s  rot=%d  live=%s  fallback=%s",
            path, self.width, self.height, self.fps, self.codec_str,
            self.rotation, self.is_live, self._fallback_used
        )

    # ── internal ─────────────────────────────────────────────────────────────

    @staticmethod
    def _open(path: str) -> cv2.VideoCapture:
        cap = cv2.VideoCapture(path)
        # For RTSP: set a short buffer to reduce latency
        if _is_live(path):
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 3)
        return cap

    def _transcode_and_open(self, path: str) -> cv2.VideoCapture:
        tmp = path + ".chorus_tc.mp4"
        self._transcoded_path = tmp
        if not os.path.exists(tmp):
            log.info("VideoReader: transcoding %s → %s via ffmpeg", path, tmp)
            cmd = [
                "ffmpeg", "-y", "-i", path,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-c:a", "aac", "-movflags", "+faststart",
                tmp
            ]
            try:
                result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=600)
                if result.returncode != 0:
                    log.error("ffmpeg transcode failed: %s", result.stderr.decode(errors="replace"))
            except FileNotFoundError:
                log.error("ffmpeg is not installed or not in PATH; skipping transcode fallback.")
        cap = cv2.VideoCapture(tmp)
        return cap

    # ── public API ────────────────────────────────────────────────────────────

    def cancel(self):
        """Signal the reader to stop iteration."""
        self._cancel.set()

    def iter_frames(
        self,
        sample_rate_fps: Optional[float] = None,
        max_frames: Optional[int] = None,
    ) -> Iterator[Tuple[int, float, Any]]:
        """
        Yield (frame_index, timestamp_seconds, frame_bgr) sequentially.

        Parameters
        ----------
        sample_rate_fps : desired output rate; frames in between are decoded but
                          not yielded (sequential; no seeking).  None = all frames.
        max_frames      : stop after this many *yielded* frames (useful for live streams).
        """
        if not self.cap.isOpened():
            return

        step = 1
        if sample_rate_fps and sample_rate_fps > 0 and self.fps > 0:
            step = max(1, int(self.fps / sample_rate_fps))

        decoded_idx = 0
        yielded = 0
        prev_pts: float = -1.0

        while True:
            if self._cancel.is_set():
                break
            if max_frames is not None and yielded >= max_frames:
                break

            ret, frame = self.cap.read()
            if not ret or frame is None:
                break

            # Timestamp: POS_MSEC (milliseconds), convert to seconds.
            # Protect against bogus 0.0 repeats (VFR edge case).
            pts_ms = self.cap.get(cv2.CAP_PROP_POS_MSEC)
            if pts_ms > 0:
                ts = pts_ms / 1000.0
            else:
                ts = decoded_idx / self.fps if self.fps > 0 else 0.0

            # Guard against non-monotone PTS (some demuxers reset)
            if ts < prev_pts and not self.is_live:
                ts = prev_pts + (1.0 / self.fps)
            prev_pts = ts

            if decoded_idx % step == 0:
                # Apply rotation
                out_frame = _rotate_frame(frame, self.rotation) if self.rotation else frame
                yield (decoded_idx, ts, out_frame)
                yielded += 1

            decoded_idx += 1

    def release(self):
        """Release the capture handle."""
        if self.cap and self.cap.isOpened():
            self.cap.release()

    def get_metadata(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "fps": round(self.fps, 4),
            "width": self.width,
            "height": self.height,
            "total_frames": self.total_frames,
            "codec": self.codec_str,
            "rotation": self.rotation,
            "is_live": self.is_live,
            "fallback_used": self._fallback_used,
            "duration_seconds": round(self.total_frames / self.fps, 3) if self.fps > 0 and self.total_frames > 0 else None,
        }
