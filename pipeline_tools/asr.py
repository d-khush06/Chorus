"""
pipeline_tools/asr.py
======================
Tool: asr_agent  (Whisper speech transcription)
Wraps asr_agent.transcribe_video() with the standard run(ctx) interface.
"""
from .base import ToolContext, ToolResult
import os, time


def run(ctx: ToolContext) -> ToolResult:
    t0 = time.monotonic()

    if ctx.skip_asr:
        return ToolResult.skipped("asr_agent", "--skip-asr flag set")

    video_path = ctx.video_path
    if not video_path or not os.path.exists(video_path):
        return ToolResult.skipped("asr_agent", "no local video file")

    try:
        from asr_agent import transcribe_video
        asr_result = transcribe_video(video_path)
        return ToolResult(
            tool="asr_agent",
            status="ok",
            result=asr_result,
            elapsed_ms=(time.monotonic() - t0) * 1000,
        )
    except ImportError:
        return ToolResult.skipped("asr_agent", "asr_agent module unavailable")
    except Exception as exc:
        return ToolResult.from_error("asr_agent", exc)
