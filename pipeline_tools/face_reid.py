"""
pipeline_tools/face_reid.py
============================
Tool: face_reid_agent  (InsightFace biometric re-identification)
Cyber mode, governance gated.  Wraps face_reid_agent.run_face_reid().
"""
from .base import ToolContext, ToolResult
import os, time


def run(ctx: ToolContext) -> ToolResult:
    t0 = time.monotonic()

    if not ctx.governance_approved:
        return ToolResult(
            tool="face_reid_agent",
            status="skipped",
            result={
                "status": "blocked",
                "governance_approved": False,
                "identities": [],
                "faces_detected": 0,
                "error": "Governance not approved.",
            },
            skipped_reason="governance not approved",
        )

    video_path = ctx.video_path
    if not video_path or not os.path.exists(video_path):
        return ToolResult.skipped("face_reid_agent", "no local video file")

    try:
        from face_reid_agent import run_face_reid
        result = run_face_reid(video_path=video_path, governance_approved=True)
        return ToolResult(
            tool="face_reid_agent",
            status="ok",
            result=result,
            elapsed_ms=(time.monotonic() - t0) * 1000,
        )
    except ImportError:
        return ToolResult.skipped("face_reid_agent", "module unavailable")
    except Exception as exc:
        return ToolResult.from_error("face_reid_agent", exc)
