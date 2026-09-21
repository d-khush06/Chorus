"""
pipeline_tools/base.py
======================
Base types shared by all Chorus pipeline tools.

ToolContext  — read-only dict-like context passed into every tool.run()
ToolResult   — typed dataclass returned by every tool.run()

Design notes
------------
- ToolContext is a plain dict so tools can be tested in isolation without
  importing the full pipeline.  Keys mirror the pipeline result dict keys.
- ToolResult uses __slots__ for minimal memory overhead and includes a
  to_dict() helper so results can be JSON-serialised or merged into the
  pipeline result dict directly.
- elapsed_ms is populated automatically by the TOOL_REGISTRY dispatcher
  in pipeline_runner.py; individual tools do NOT need to time themselves.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


# ── ToolContext ───────────────────────────────────────────────────────────────

class ToolContext(dict):
    """
    Thin dict subclass that provides attribute-style access to common keys
    and is passed read-only to every tool.run().

    Standard keys (all optional — tools must guard for None):
        video_path          : str | None  — local file path
        url                 : str | None  — YouTube / RTSP / HLS URL
        source_type         : str         — "local_upload" | "youtube" | "live_rtsp"
        mode                : str         — "general" | "cyber"
        user_question       : str
        governance_approved : bool
        manipulation_verdict: str         — "CLEAN" | "FLAGGED"
        fast_mode           : bool
        skip_vl             : bool
        skip_asr            : bool
        scenes              : list
        asr_result          : dict | None
        vl_output           : str | None
        engine_profile      : dict | None
        acoustic_result     : dict | None
        geo_result          : dict | None
        face_reid_result    : dict | None
        alert_result        : dict | None
        verification_result : dict | None
        video_title         : str | None
        video_id            : str | None
        playlist_index      : int | None
        playlist_total      : int | None
        extracted_frames    : list        — PIL frames for VL agent
        key_features        : dict
    """

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            return None

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


# ── ToolResult ────────────────────────────────────────────────────────────────

@dataclass
class ToolResult:
    """
    Standard return type from every pipeline_tool.run() call.

    Fields
    ------
    tool        : canonical tool name (matches TOOL_REGISTRY key)
    status      : "ok" | "skipped" | "error"
    result      : the raw tool output dict (pass-through to pipeline result)
    error       : error message string if status == "error", else None
    elapsed_ms  : wall-clock ms for this tool (set by dispatcher, not the tool)
    skipped_reason : human-readable reason if status == "skipped"
    """
    tool:           str
    status:         str          = "ok"
    result:         dict         = field(default_factory=dict)
    error:          Optional[str] = None
    elapsed_ms:     float        = 0.0
    skipped_reason: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def skipped(cls, tool: str, reason: str) -> "ToolResult":
        return cls(tool=tool, status="skipped", skipped_reason=reason)

    @classmethod
    def from_error(cls, tool: str, exc: Exception) -> "ToolResult":
        return cls(tool=tool, status="error", error=str(exc))
