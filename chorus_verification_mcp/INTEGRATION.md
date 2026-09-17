# INTEGRATION.md
# ==============
# Chorus Verification MCP — Orchestrator Integration Guide
#
# This document describes how the Chorus pipeline Orchestrator (Step 6 / pipeline_runner.py)
# should connect to the chorus_verification_mcp server once it is ready to be wired in.
# No code changes to any existing Chorus file are made here — this is documentation only.

# ─────────────────────────────────────────────────────────────────────────────
# Overview
# ─────────────────────────────────────────────────────────────────────────────

The `chorus_verification_mcp` server exposes four external-verification tools over
the Model Context Protocol (MCP) using stdio transport.  The Orchestrator connects
to it as an MCP *client*, discovers tools at startup, and calls them on-demand
when internal pipeline signals indicate a frame, source, or claim needs outside
corroboration.

# ─────────────────────────────────────────────────────────────────────────────
# Connection method
# ─────────────────────────────────────────────────────────────────────────────

Transport: **stdio** (standard MCP local process transport).

The Orchestrator spawns the verification server as a subprocess and communicates
over its stdin/stdout using the MCP protocol.  This keeps the server isolated
from the main pipeline process and allows it to be restarted independently.

## Python (using the official `mcp` SDK client)

```python
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

server_params = StdioServerParameters(
    command="python",
    args=["/path/to/chorus_verification_mcp/server.py"],
    env={
        "YOUTUBE_API_KEY":    "<key>",
        "FACTCHECK_API_KEY":  "<key>",
        "SERPER_API_KEY":     "<key>",
        "GOOGLE_CSE_API_KEY": "<key>",
        "GOOGLE_CSE_CX":      "<cx-id>",
    },
)

async def verify_claim(claim: str, case_id: str):
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool(
                "fact_check_claim",
                arguments={"claim_text": claim, "case_id": case_id},
            )
            return result
```

## Alternative: pre-started server via environment

If the Orchestrator is configured to use a long-lived MCP server (e.g. started
by a process supervisor), pass the server's stdio file descriptors or use an
SSE transport if the server is adapted to support it in a future revision.

# ─────────────────────────────────────────────────────────────────────────────
# Registered tool names (exact strings for call_tool())
# ─────────────────────────────────────────────────────────────────────────────

| Tool name                | When to call                                                    |
|--------------------------|------------------------------------------------------------------|
| `reverse_search_frame`   | manipulation_detection returns `verdict="FLAGGED"`              |
| `check_upload_history`   | source_type is `youtube`; temporal claim requires verification  |
| `fact_check_claim`       | ASR or OCR text contains a verifiable factual assertion         |
| `web_search_fetch`       | General fallback; fact-check returns `unverified`               |

# ─────────────────────────────────────────────────────────────────────────────
# Discovery
# ─────────────────────────────────────────────────────────────────────────────

After `session.initialize()`, call `session.list_tools()` to get the full input
schemas for all four tools.  This allows the Orchestrator to validate arguments
before calling or to pass schemas to an LLM for structured generation.

```python
tools = await session.list_tools()
# tools.tools is a list of mcp.types.Tool with .name and .inputSchema
```

# ─────────────────────────────────────────────────────────────────────────────
# Conditional invocation (important)
# ─────────────────────────────────────────────────────────────────────────────

Do NOT call all four tools on every video.  Wire them behind the appropriate
internal pipeline signals to stay within free-tier API quotas:

```
manipulation_detection.verdict == "FLAGGED"
    → reverse_search_frame (verify frame origin)
    → web_search_fetch (search for context)

source_type == "youtube"
    → check_upload_history (verify upload date)

asr_agent.transcript contains a factual claim
    → fact_check_claim
    → web_search_fetch (if verdict == "unverified")
```

# ─────────────────────────────────────────────────────────────────────────────
# Environment variables required by the server
# ─────────────────────────────────────────────────────────────────────────────

See `.env.example` for the full list.  Pass them via the `env` dict in
`StdioServerParameters` or export them into the shell environment before
starting the server.

# ─────────────────────────────────────────────────────────────────────────────
# Audit log location
# ─────────────────────────────────────────────────────────────────────────────

Every tool call is logged (append-only JSONL) to:

    chorus_verification_mcp/audit_logs/verification_mcp/verification_mcp_<YYYY-MM-DD>.jsonl

Log entries follow the Chorus-standard shape:
    {timestamp, case_id, actor, action, detail}

The Orchestrator can read these logs after a pipeline run to reconstruct the
full verification trail for a given `case_id`.
