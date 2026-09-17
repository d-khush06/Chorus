"""
audit.py
========
Chorus Verification MCP — Audit logging helper.

Mirrors exactly the _append_audit_log pattern from project_manager.py:
  • Append-only JSONL, one file per calendar day.
  • Log directory: audit_logs/verification_mcp/
  • Line shape: {timestamp, case_id, actor, action, detail}

Every tool call emits TWO log lines:
  1. "tool_call_start"  — written immediately before the external request,
                          so a slow/crashed call is visible in the trail.
  2. "tool_call_result" — written on success or structured error return.

This module has no dependencies on the MCP SDK or the tool modules and
can be imported standalone for testing.
"""

import os
import json
import datetime
import logging

import config

# ---------------------------------------------------------------------------
# Module-level logger
# ---------------------------------------------------------------------------
log = logging.getLogger("chorus.verification_mcp.audit")

# Actor label written into every log line produced by this MCP server.
MCP_ACTOR: str = "chorus_verification_mcp"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def append_audit_log(
    case_id: str,
    actor: str,
    action: str,
    detail: dict,
) -> None:
    """
    Append one audit entry to today's daily JSONL log.

    File path: <AUDIT_LOG_DIR>/verification_mcp_<YYYY-MM-DD>.jsonl

    Fields per line (matches project_manager.py _append_audit_log shape):
        {timestamp, case_id, actor, action, detail}

    Never raises — audit failures are logged to stderr but must not
    block or abort a tool call.
    """
    try:
        os.makedirs(config.AUDIT_LOG_DIR, exist_ok=True)
        date_str = datetime.date.today().isoformat()
        log_path = os.path.join(
            config.AUDIT_LOG_DIR, f"verification_mcp_{date_str}.jsonl"
        )
        entry = {
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "case_id":   case_id,
            "actor":     actor,
            "action":    action,
            "detail":    detail,
        }
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        log.debug("Audit entry written: action=%s case_id=%s", action, case_id)
    except Exception as log_err:
        log.error("Failed to write audit log: %s", log_err)


def log_tool_start(
    tool_name: str,
    case_id: str,
    inputs: dict,
) -> None:
    """
    Emit the pre-call audit line for a tool invocation.

    Raw API keys are never logged; the inputs dict is assumed to be
    already sanitised by the caller (tool modules strip keys before
    passing to this function).
    """
    append_audit_log(
        case_id=case_id,
        actor=MCP_ACTOR,
        action="tool_call_start",
        detail={
            "tool":   tool_name,
            "inputs": inputs,
        },
    )


def log_tool_result(
    tool_name: str,
    case_id: str,
    result: dict,
) -> None:
    """
    Emit the post-call audit line for a tool invocation.

    *result* should be the full structured response (including any
    error fields) as returned to the MCP client.
    """
    append_audit_log(
        case_id=case_id,
        actor=MCP_ACTOR,
        action="tool_call_result",
        detail={
            "tool":   tool_name,
            "result": result,
        },
    )
