"""
video_engine/engine.py
======================
Single-pass video engine.

Rules
-----
- Decode ONCE. No seeking. All analyzers receive every sampled frame.
- Downscale is applied before fan-out; analyzers see smaller frames.
- Bounded memory: frames are not accumulated.
- Cancel support: VideoReader.cancel() + engine._cancel_flag.
- Checkpointing: the last processed frame_idx and ts are saved to
  <checkpoint_path> so a crashed long run can resume (analyzers that
  support resume() will be called).
- Progress: emits a dict every 30 decoded frames via progress_callback.
- For live RTSP: max_frames_live caps the run to a finite chunk.
"""

import cv2
import time
import json
import os
import logging
from typing import List, Dict, Any, Callable, Optional
from .reader import VideoReader
from .analyzers.base import BaseAnalyzer

log = logging.getLogger("chorus.video_engine.engine")

_LIVE_CHUNK_FRAMES_DEFAULT = 750  # ~30 s at 25 fps


class VideoEngine:
    """
    Centralized single-pass video analysis engine.

    Parameters
    ----------
    video_path          : local file path or RTSP/HTTP URL.
    max_downscale_width : if >0 and source wider, frames are downscaled.
    checkpoint_path     : JSON file where progress is persisted (optional).
    """

    def __init__(
        self,
        video_path: str,
        max_downscale_width: int = 640,
        checkpoint_path: Optional[str] = None,
    ):
        self.video_path = video_path
        self.max_downscale_width = max_downscale_width
        self.checkpoint_path = checkpoint_path
        self.analyzers: List[BaseAnalyzer] = []
        self._cancel_flag = False
        self._reader: Optional[VideoReader] = None

    def add_analyzer(self, analyzer: BaseAnalyzer) -> "VideoEngine":
        self.analyzers.append(analyzer)
        return self

    def cancel(self):
        self._cancel_flag = True
        if self._reader:
            self._reader.cancel()

    def run(
        self,
        sample_rate_fps: float = 0.0,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        max_frames_live: int = _LIVE_CHUNK_FRAMES_DEFAULT,
    ) -> Dict[str, Any]:
        """
        Execute a single decode pass; return full results dict.

        Parameters
        ----------
        sample_rate_fps  : target frames/sec to yield (0 = all frames).
        progress_callback: called with a dict every ~30 yielded frames.
        max_frames_live  : hard cap for live streams to bound the chunk.

        Returns
        -------
        {
          "metadata": {...},
          "performance": {...},
          "analyzers": { name: finalize_result }
        }
        """
        start_time = time.time()
        self._cancel_flag = False

        # ── Open reader ───────────────────────────────────────────────────────
        try:
            reader = VideoReader(self.video_path)
        except RuntimeError as exc:
            log.error("VideoEngine: cannot open source: %s", exc)
            return {
                "metadata": {"path": self.video_path, "error": str(exc)},
                "performance": {},
                "analyzers": {a.name: {"status": "skipped", "reason": str(exc)} for a in self.analyzers},
            }

        self._reader = reader
        meta = reader.get_metadata()

        # ── Downscale target ──────────────────────────────────────────────────
        target_size: Optional[tuple] = None
        if self.max_downscale_width and meta["width"] > self.max_downscale_width:
            ratio = self.max_downscale_width / float(meta["width"])
            target_size = (self.max_downscale_width, int(meta["height"] * ratio))
            log.info("VideoEngine: downscaling %dx%d → %dx%d",
                     meta["width"], meta["height"], *target_size)

        # ── Resume from checkpoint ─────────────────────────────────────────
        resume_from_idx = 0
        if self.checkpoint_path and os.path.exists(self.checkpoint_path):
            try:
                with open(self.checkpoint_path) as f:
                    ckpt = json.load(f)
                resume_from_idx = int(ckpt.get("last_frame_idx", 0))
                log.info("VideoEngine: resuming from frame %d", resume_from_idx)
            except Exception:
                pass

        total_frames = meta.get("total_frames", 0)
        frames_processed = 0
        last_ts = 0.0

        # Live streams use a frame cap; files iterate to end
        max_frames = max_frames_live if reader.is_live else None

        # ── Main loop ─────────────────────────────────────────────────────────
        for frame_idx, ts, frame in reader.iter_frames(sample_rate_fps or None, max_frames=max_frames):
            if self._cancel_flag:
                log.info("VideoEngine: cancelled at frame %d", frame_idx)
                break

            # Resume: skip already-processed frames (cheap; we must still decode)
            if frame_idx < resume_from_idx:
                continue

            # Downscale
            process_frame = frame
            if target_size:
                process_frame = cv2.resize(frame, target_size, interpolation=cv2.INTER_AREA)

            # Fan-out to analyzers
            for analyzer in self.analyzers:
                try:
                    analyzer.on_frame(process_frame, ts, frame_idx)
                except Exception as exc:
                    log.warning("Analyzer %s raised at frame %d: %s", analyzer.name, frame_idx, exc)

            frames_processed += 1
            last_ts = ts

            # Progress callback every ~30 frames
            if progress_callback and frames_processed % 30 == 0:
                pct = (frame_idx / total_frames) if total_frames > 0 else 0.0
                try:
                    progress_callback({
                        "event": "STAGE_EVENT",
                        "stage": "video_engine",
                        "progress": round(min(1.0, pct), 4),
                        "frame_idx": frame_idx,
                        "ts": round(ts, 3),
                    })
                except Exception:
                    pass

            # Checkpoint every 300 frames
            if self.checkpoint_path and frames_processed % 300 == 0:
                try:
                    with open(self.checkpoint_path, "w") as f:
                        json.dump({"last_frame_idx": frame_idx, "last_ts": ts}, f)
                except Exception:
                    pass

        reader.release()
        self._reader = None

        # Clean up checkpoint on successful completion
        if self.checkpoint_path and os.path.exists(self.checkpoint_path) and not self._cancel_flag:
            try:
                os.remove(self.checkpoint_path)
            except Exception:
                pass

        elapsed = time.time() - start_time

        # ── Finalize analyzers ────────────────────────────────────────────────
        analyzer_results: Dict[str, Any] = {}
        for analyzer in self.analyzers:
            try:
                analyzer_results[analyzer.name] = analyzer.finalize()
            except Exception as exc:
                log.warning("Analyzer %s finalize() raised: %s", analyzer.name, exc)
                analyzer_results[analyzer.name] = {"status": "error", "reason": str(exc)}

        return {
            "metadata": {
                **meta,
                "total_frames": max(total_frames, frames_processed),
            },
            "performance": {
                "frames_processed": frames_processed,
                "elapsed_seconds": round(elapsed, 3),
                "fps_throughput": round(frames_processed / elapsed, 2) if elapsed > 0 else 0,
                "last_ts_processed": round(last_ts, 3),
                "cancelled": self._cancel_flag,
            },
            "analyzers": analyzer_results,
        }
