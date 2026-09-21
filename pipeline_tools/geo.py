"""
pipeline_tools/geo.py
======================
Tool: geo_estimation_agent  (GeoCLIP geo estimation)
Cyber mode only.  Wraps geo_estimation_agent.estimate_geo().
"""
from .base import ToolContext, ToolResult
import os, time


def run(ctx: ToolContext) -> ToolResult:
    t0 = time.monotonic()

    video_path = ctx.video_path
    if not video_path or not os.path.exists(video_path):
        return ToolResult.skipped("geo_estimation_agent", "no local video file")

    try:
        from geo_estimation_agent import estimate_geo
        result = estimate_geo(video_path=video_path)
        return ToolResult(
            tool="geo_estimation_agent",
            status="ok",
            result=result,
            elapsed_ms=(time.monotonic() - t0) * 1000,
        )
    except ImportError:
        return ToolResult.skipped("geo_estimation_agent", "module unavailable")
    except Exception as exc:
        return ToolResult.from_error("geo_estimation_agent", exc)
