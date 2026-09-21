"""
pipeline_tools/__init__.py
===========================
Chorus Pipeline Tools — Hermes-style plugin directory.

Each tool module exposes:
    run(ctx: ToolContext) -> ToolResult

The TOOL_REGISTRY in pipeline_runner.py maps orchestrator tool_call names
to these run() callables.  The orchestrator is free to include, exclude, or
reorder any tool at inference time without touching the pipeline body.

Public exports
--------------
    ToolContext  - frozen context dict passed to every tool
    ToolResult   - typed return value (dataclass)
    TOOL_REGISTRY- name -> run() mapping used by pipeline_runner.py
"""

from .base import ToolContext, ToolResult

from . import scene_segmentation
from . import perception
from . import asr
from . import video_engine as video_engine_tool
from . import acoustic
from . import geo
from . import face_reid
from . import alert
from . import fusion
from . import domain_output

# ─────────────────────────────────────────────────────────────────────────────
# TOOL_REGISTRY
# Maps orchestrator tool_call names → run(ctx) callables
# Add new tools here; no changes required in pipeline_runner.py.
# ─────────────────────────────────────────────────────────────────────────────
TOOL_REGISTRY: dict = {
    "scene_segmentation":       scene_segmentation.run,
    "perception_agent":         perception.run,
    "asr_agent":                asr.run,
    "video_engine":             video_engine_tool.run,
    "acoustic_event_detection": acoustic.run,
    "geo_estimation_agent":     geo.run,
    "face_reid_agent":          face_reid.run,
    "alert_system":             alert.run,
    "fusion_agent":             fusion.run,
    "domain_output":            domain_output.run,
}

__all__ = ["ToolContext", "ToolResult", "TOOL_REGISTRY"]
