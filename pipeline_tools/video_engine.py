"""
pipeline_tools/video_engine.py
================================
Tool: video_engine  (deterministic single-pass signal layer)
Wraps the VideoEngine + VideoProfile with the standard run(ctx) interface.
"""
from .base import ToolContext, ToolResult
import os, time


def run(ctx: ToolContext) -> ToolResult:
    t0 = time.monotonic()

    # Accept local file OR live RTSP URL
    source = ctx.video_path if (ctx.video_path and os.path.exists(ctx.video_path)) \
             else (ctx.url if ctx.source_type == "live_rtsp" else None)

    if not source:
        return ToolResult.skipped("video_engine", "no video source available")

    try:
        from video_engine import (
            VideoEngine, TechnicalAnalyzer, MotionAnalyzer, ShotsAnalyzer,
            ObjectAnalyzer, FaceAnalyzer, TextAndCodeAnalyzer, SimilarityAnalyzer,
            VideoProfile,
        )

        engine = VideoEngine(source)
        engine.add_analyzer(TechnicalAnalyzer())
        engine.add_analyzer(MotionAnalyzer(compute_heatmap=False))
        engine.add_analyzer(ShotsAnalyzer(mode=ctx.mode or "general"))
        engine.add_analyzer(TextAndCodeAnalyzer())
        if ctx.mode == "cyber":
            engine.add_analyzer(ObjectAnalyzer())
            if ctx.governance_approved:
                engine.add_analyzer(FaceAnalyzer())
            engine.add_analyzer(SimilarityAnalyzer())

        raw = engine.run()
        profile = VideoProfile(
            run_id=os.path.basename(source) if ctx.video_path else "rtsp_stream"
        )
        profile.populate(raw)

        return ToolResult(
            tool="video_engine",
            status="ok",
            result=profile.data,
            elapsed_ms=(time.monotonic() - t0) * 1000,
        )
    except ImportError:
        return ToolResult.skipped("video_engine", "video_engine module unavailable")
    except Exception as exc:
        return ToolResult.from_error("video_engine", exc)
