"""
pipeline_tools/perception.py
=============================
Tool: perception_agent  (VL vision analysis)
Wraps run_vl_agent.run_vision_analysis() with the standard run(ctx) interface.
"""
from .base import ToolContext, ToolResult
import time


def run(ctx: ToolContext) -> ToolResult:
    t0 = time.monotonic()

    if ctx.skip_vl:
        return ToolResult.skipped("perception_agent", "--skip-vl flag set")

    video_path = ctx.video_path
    frames = list(ctx.extracted_frames or [])

    if not frames and not video_path:
        return ToolResult.skipped("perception_agent", "no frames and no video path")

    try:
        from run_vl_agent import run_vision_analysis
        import os

        if not frames and video_path and os.path.exists(video_path):
            from chorus_input import LocalAdapter
            adapter = LocalAdapter()
            payload = adapter.process(video_path, "local_video")
            frames = payload.frames

        if not frames:
            return ToolResult.skipped("perception_agent", "no frames extracted")

        vl_meta = dict(ctx.key_features or {})
        vl_meta.update({
            "ai_generated_flag": ctx.manipulation_verdict == "FLAGGED",
            "deepfake_flag":     ctx.manipulation_verdict == "FLAGGED",
        })

        vl_output = run_vision_analysis(frames, ctx.user_question or "", vl_meta)
        return ToolResult(
            tool="perception_agent",
            status="ok",
            result={"vl_output": vl_output, "frames_analyzed": len(frames)},
            elapsed_ms=(time.monotonic() - t0) * 1000,
        )
    except ImportError:
        return ToolResult.skipped("perception_agent", "run_vl_agent module unavailable")
    except Exception as exc:
        return ToolResult.from_error("perception_agent", exc)
