"""
Orion MCP Server
========================
FastMCP server that exposes all Orion tools over SSE.

The LiveKit voice agent connects to this server to discover and invoke
tools at runtime. Each tool delegates execution to the OpenClaw daemon.

Run:
    uv run orion_server
"""

from __future__ import annotations

import asyncio
import logging

from mcp.server.fastmcp import FastMCP
from orion.tools import register_all_tools
from orion.config import config
from bridge import get_openclaw_client

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-20s  %(levelname)-7s  %(message)s",
)
logger = logging.getLogger("orion.server")

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name=config.server_name,
    instructions=(
        "You are Orion, a voice-first AI assistant. "
        "You have access to tools that connect to the OpenClaw daemon "
        "for executing real-world tasks. Be concise and precise."
    ),
)

# Register all tool modules
register_all_tools(mcp)


# ---------------------------------------------------------------------------
# Startup health check
# ---------------------------------------------------------------------------

async def _startup_health_check() -> None:
    """Log OpenClaw daemon status on server boot."""
    client = get_openclaw_client()
    healthy = await client.health_check()
    if healthy:
        skills = await client.list_skills()
        logger.info("✓ OpenClaw daemon is ONLINE at %s", config.openclaw_url)
        if skills:
            logger.info("  Available agents/models: %s", ", ".join(skills))
    else:
        logger.warning(
            "✗ OpenClaw daemon is OFFLINE at %s — tools will return error messages.",
            config.openclaw_url,
        )
        logger.warning(
            "  Start OpenClaw with: openclaw gateway --port 18789"
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    """Start the FastMCP server with SSE transport."""
    logger.info("Orion MCP Server starting on port %d…", config.mcp_server_port)

    # Run the health check before starting the server
    asyncio.get_event_loop().run_until_complete(_startup_health_check())

    logger.info("MCP Server ready — SSE transport on http://127.0.0.1:%d/sse", config.mcp_server_port)
    mcp.run(transport="sse")


if __name__ == "__main__":
    main()
