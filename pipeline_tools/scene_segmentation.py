"""
pipeline_tools/scene_segmentation.py
=====================================
Tool: scene_segmentation
Wraps scene_segmentation.detect_scenes() with the standard run(ctx) interface.
"""
from .base import ToolContext, ToolResult
import os, time


def run(ctx: ToolContext) -> ToolResult:
    t0 = time.monotonic()
    video_path = ctx.video_path

    if not video_path or not os.path.exists(video_path):
        return ToolResult.skipped("scene_segmentation", "no local video file")

    try:
        from scene_segmentation import detect_scenes
        seg_result = detect_scenes({
            "video_path": video_path,
            "source_type": ctx.source_type or "local_upload",
            "mode": ctx.mode or "general",
        })
        return ToolResult(
            tool="scene_segmentation",
            status="ok",
            result=seg_result,
            elapsed_ms=(time.monotonic() - t0) * 1000,
        )
    except ImportError:
        return ToolResult.skipped("scene_segmentation", "scene_segmentation module unavailable")
    except Exception as exc:
        return ToolResult.from_error("scene_segmentation", exc)
