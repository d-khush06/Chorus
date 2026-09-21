"""
pipeline_tools/acoustic.py
===========================
Tool: acoustic_event_detection  (YAMNet audio classification)
Cyber mode only.  Wraps acoustic_event_detection.detect_acoustic_events().
"""
from .base import ToolContext, ToolResult
import os, time


def run(ctx: ToolContext) -> ToolResult:
    t0 = time.monotonic()

    video_path = ctx.video_path
    if not video_path or not os.path.exists(video_path):
        return ToolResult.skipped("acoustic_event_detection", "no local video file")

    try:
        from acoustic_event_detection import detect_acoustic_events
        result = detect_acoustic_events(video_path)
        return ToolResult(
            tool="acoustic_event_detection",
            status="ok",
            result=result,
            elapsed_ms=(time.monotonic() - t0) * 1000,
        )
    except ImportError:
        return ToolResult.skipped("acoustic_event_detection", "module unavailable")
    except Exception as exc:
        return ToolResult.from_error("acoustic_event_detection", exc)
