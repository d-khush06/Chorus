"""
pipeline_tools/alert.py
========================
Tool: alert_system
Cyber mode only.  Wraps alert_system.evaluate_and_alert().
"""
from .base import ToolContext, ToolResult
import time


def run(ctx: ToolContext) -> ToolResult:
    t0 = time.monotonic()

    try:
        from alert_system import evaluate_and_alert
        result = evaluate_and_alert(
            acoustic_result=ctx.acoustic_result,
            geo_result=ctx.geo_result,
            face_reid_result=ctx.face_reid_result,
            manipulation_result=ctx.get("manipulation_result"),
            source_uri=ctx.video_path or ctx.url or "",
        )
        return ToolResult(
            tool="alert_system",
            status="ok",
            result=result,
            elapsed_ms=(time.monotonic() - t0) * 1000,
        )
    except ImportError:
        return ToolResult.skipped("alert_system", "module unavailable")
    except Exception as exc:
        return ToolResult.from_error("alert_system", exc)
