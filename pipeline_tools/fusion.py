"""
pipeline_tools/fusion.py
=========================
Tool: fusion_agent
Wraps fusion_agent.fuse_pipeline_outputs() with the standard run(ctx) interface.
"""
from .base import ToolContext, ToolResult
import time


def run(ctx: ToolContext) -> ToolResult:
    t0 = time.monotonic()

    try:
        from fusion_agent import fuse_pipeline_outputs

        manipulation_result = ctx.get("manipulation_result") or {}
        deepfake_flag = manipulation_result.get("verdict") == "FLAGGED"

        meta = {
            "video_duration_seconds": (ctx.get("scene_result") or {}).get("duration_s"),
        }
        meta.update(manipulation_result)

        result = fuse_pipeline_outputs(
            scenes=ctx.scenes or [],
            asr_result=ctx.asr_result,
            vl_output=ctx.vl_output,
            metadata=meta,
            source_type=ctx.source_type or "local_upload",
            source_uri=ctx.video_path or ctx.url or "",
            deepfake_flag=deepfake_flag,
            ai_generated_flag=deepfake_flag,
            mode=ctx.mode or "general",
            acoustic_result=ctx.acoustic_result,
            geo_result=ctx.geo_result,
            face_reid_result=ctx.face_reid_result,
            alert_result=ctx.alert_result,
            verification_result=ctx.verification_result,
            engine_profile=ctx.engine_profile,
        )
        return ToolResult(
            tool="fusion_agent",
            status="ok",
            result=result,
            elapsed_ms=(time.monotonic() - t0) * 1000,
        )
    except ImportError:
        return ToolResult.skipped("fusion_agent", "fusion_agent module unavailable")
    except Exception as exc:
        return ToolResult.from_error("fusion_agent", exc)
