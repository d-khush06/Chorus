"""
pipeline_tools/domain_output.py
================================
Tool: domain_output
Wraps domain_output.generate_output() with the standard run(ctx) interface.
"""
from .base import ToolContext, ToolResult
import os, time


def run(ctx: ToolContext) -> ToolResult:
    t0 = time.monotonic()

    fusion_result = ctx.get("fusion_result")
    if not fusion_result:
        return ToolResult.skipped("domain_output", "no fusion result available")

    try:
        from domain_output import generate_output

        video_title = ctx.video_title
        if not video_title and ctx.video_path:
            video_title = os.path.basename(ctx.video_path)

        result = generate_output(
            fused=fusion_result,
            user_question=ctx.user_question or "",
            mode=ctx.mode or "general",
        )
        return ToolResult(
            tool="domain_output",
            status="ok",
            result=result,
            elapsed_ms=(time.monotonic() - t0) * 1000,
        )
    except ImportError:
        return ToolResult.skipped("domain_output", "domain_output module unavailable")
    except Exception as exc:
        return ToolResult.from_error("domain_output", exc)
