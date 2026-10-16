"""
Tool registry — imports and registers all tool modules with the MCP server.

To add a new capability:
1. Create a new file in this directory (e.g. ``music.py``)
2. Define a ``register(mcp, runtime)`` function inside it
3. Import and call it here
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from orion.tools import (
    email,
    messaging,
    calendar,
    code,
    files,
    browser,
    system,
    memory,
)

if TYPE_CHECKING:
    from orion.core.runtime import Runtime


def register_all_tools(mcp, runtime: Runtime) -> None:
    """Register every tool group onto the given MCP server instance."""
    for module in (email, messaging, calendar, code, files, browser, system, memory):
        module.register(mcp, runtime)
