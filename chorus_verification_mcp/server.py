"""
server.py
=========
Chorus Verification MCP — Server Entry Point

# ─────────────────────────────────────────────────────────────────────────────
# CONDITIONAL INVOCATION NOTE (for Orchestrator integration authors)
# ─────────────────────────────────────────────────────────────────────────────
# The four tools registered here are meant to be called ON-DEMAND, not
# unconditionally on every video processed by the Chorus pipeline.
#
# Recommended trigger conditions (Orchestrator / Step 6):
#   • reverse_search_frame  — when manipulation_detection.py returns
#                             verdict="FLAGGED" or confidence < threshold.
#   • check_upload_history  — when source type is "youtube" and temporal
#                             context of the claim is important.
#   • fact_check_claim      — when ASR or on-screen text contains a
#                             verifiable factual assertion.
#   • web_search_fetch      — as a general fallback when the above tools
#                             return "unverified" or when the Orchestrator
#                             needs additional corroboration.
#
# Calling all four tools on every video would exhaust free-tier API quotas
# quickly.  Wire them behind the appropriate confidence/flag checks.
# ─────────────────────────────────────────────────────────────────────────────

Server startup behaviour
------------------------
1. Load and validate all required API keys (fails loudly if any are missing).
2. Print a startup summary banner listing each tool and key status.
3. Register four MCP tools with full JSON-schema annotations.
4. Run the MCP server over stdio (the standard transport for local MCP servers).

Usage
-----
  python server.py

Or via the MCP dev runner (if installed):
  mcp dev server.py
"""

import asyncio
import logging
import os
import sys

# Ensure the package directory is on sys.path so sibling modules import cleanly
# whether the server is started from inside or outside the directory.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import config
from tools import reverse_search, upload_history, fact_check, web_search_fetch

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[chorus_verification_mcp] %(levelname)s -- %(message)s",
)
log = logging.getLogger("chorus.verification_mcp.server")

# ---------------------------------------------------------------------------
# MCP Server instance
# ---------------------------------------------------------------------------
server = Server("chorus-verification-mcp")

# ---------------------------------------------------------------------------
# Tool registration — explicit JSON input/output schemas
# ---------------------------------------------------------------------------

# ── Tool 1: reverse_search_frame ─────────────────────────────────────────────
@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """Enumerate all four verification tools for discovery by MCP clients."""
    return [
        types.Tool(
            name="reverse_search_frame",
            description=(
                "Reverse-image-search a video frame against the web to find "
                "where it has appeared online, including the earliest known source "
                "and similarity scores. Pass a public HTTPS image URL as 'image'."
            ),
            inputSchema={
                "type": "object",
                "required": ["image", "case_id"],
                "properties": {
                    "image": {
                        "type": "string",
                        "description": (
                            "Public HTTPS URL of the frame image, a local file path, "
                            "or a base64-encoded image string."
                        ),
                    },
                    "case_id": {
                        "type": "string",
                        "description": "Chorus case ID for audit correlation.",
                    },
                },
                "additionalProperties": False,
            },
        ),

        # ── Tool 2: check_upload_history ─────────────────────────────────────
        types.Tool(
            name="check_upload_history",
            description=(
                "Query the YouTube Data API v3 to verify when a video was first "
                "published, the channel that published it, and whether other copies "
                "exist on YouTube (potential re-uploads)."
            ),
            inputSchema={
                "type": "object",
                "required": ["video_url_or_id", "case_id"],
                "properties": {
                    "video_url_or_id": {
                        "type": "string",
                        "description": (
                            "Full YouTube video URL "
                            "(e.g. https://www.youtube.com/watch?v=XXXXXXXXXXX) "
                            "or a bare 11-character video ID."
                        ),
                    },
                    "case_id": {
                        "type": "string",
                        "description": "Chorus case ID for audit correlation.",
                    },
                },
                "additionalProperties": False,
            },
        ),

        # ── Tool 3: fact_check_claim ──────────────────────────────────────────
        types.Tool(
            name="fact_check_claim",
            description=(
                "Use the Google Fact Check Tools API to search existing third-party "
                "fact-checks for the supplied claim text. Returns a verdict and a "
                "list of matching fact-check sources."
            ),
            inputSchema={
                "type": "object",
                "required": ["claim_text", "case_id"],
                "properties": {
                    "claim_text": {
                        "type": "string",
                        "maxLength": 1000,
                        "description": (
                            "The verbatim claim or statement to fact-check. "
                            "Taken directly from ASR transcript or on-screen text."
                        ),
                    },
                    "case_id": {
                        "type": "string",
                        "description": "Chorus case ID for audit correlation.",
                    },
                },
                "additionalProperties": False,
            },
        ),

        # ── Tool 4: web_search_fetch ──────────────────────────────────────────
        types.Tool(
            name="web_search_fetch",
            description=(
                "Dual-mode web tool. "
                "mode='search': run a web search and return title/URL/snippet results. "
                "mode='fetch': directly fetch a URL and return extracted plain-text content."
            ),
            inputSchema={
                "type": "object",
                "required": ["case_id", "mode"],
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query string. Required when mode='search'.",
                    },
                    "case_id": {
                        "type": "string",
                        "description": "Chorus case ID for audit correlation.",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["search", "fetch"],
                        "description": "'search' to run a web query; 'fetch' to retrieve a URL.",
                    },
                    "url": {
                        "type": "string",
                        "description": (
                            "URL to fetch. Required when mode='fetch'. "
                            "Must begin with http:// or https://."
                        ),
                    },
                },
                "additionalProperties": False,
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Tool call dispatcher
# ---------------------------------------------------------------------------

@server.call_tool()
async def call_tool(
    name: str,
    arguments: dict,
) -> list[types.TextContent]:
    """
    Route incoming tool calls to the appropriate implementation module.
    All tool functions are synchronous; we run them in a thread-pool executor
    to avoid blocking the asyncio event loop.
    """
    loop = asyncio.get_event_loop()

    if name == "reverse_search_frame":
        result = await loop.run_in_executor(None, reverse_search.run, arguments)
    elif name == "check_upload_history":
        result = await loop.run_in_executor(None, upload_history.run, arguments)
    elif name == "fact_check_claim":
        result = await loop.run_in_executor(None, fact_check.run, arguments)
    elif name == "web_search_fetch":
        result = await loop.run_in_executor(None, web_search_fetch.run, arguments)
    else:
        result = {
            "error":  True,
            "reason": f"Unknown tool: {name!r}",
            "case_id": arguments.get("case_id", "unknown"),
        }

    import json
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


# ---------------------------------------------------------------------------
# Startup summary banner
# ---------------------------------------------------------------------------

def _print_startup_banner(key_status: dict[str, bool]) -> None:
    """
    Print a human-readable summary of registered tools and key availability.
    This is the first thing an operator sees when starting the server, making
    misconfiguration obvious before any client connects.
    """
    tool_key_map = {
        "reverse_search_frame":  ["GOOGLE_CSE_API_KEY", "GOOGLE_CSE_CX"],
        "check_upload_history":  ["YOUTUBE_API_KEY"],
        "fact_check_claim":      ["FACTCHECK_API_KEY"],
        "web_search_fetch":      ["SERPER_API_KEY"],
    }

    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║        Chorus Verification MCP — Startup Summary            ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    for tool_name, key_names in tool_key_map.items():
        all_ok = all(key_status.get(k, False) for k in key_names)
        status_icon = "✓" if all_ok else "✗"
        key_summary = ", ".join(
            f"{k}: {'OK' if key_status.get(k) else 'MISSING'}"
            for k in key_names
        )
        print(f"║  [{status_icon}] {tool_name:<32} {key_summary}")
    print("╠══════════════════════════════════════════════════════════════╣")
    print(f"║  Transport: stdio                                            ║")
    print(f"║  Rate window: {config.RATE_WINDOW_SECONDS}s                 "
          "                              ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    # Step 1: validate config — exits loudly if keys are missing
    key_status = config.load_and_validate()

    # Step 2: startup banner
    _print_startup_banner(key_status)

    log.info("Starting Chorus Verification MCP server over stdio …")

    # Step 3: run the MCP server
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
