"""
Tool registry — imports and registers all tool modules with the MCP server.

To add a new capability:
1. Create a new file in this directory (e.g. ``music.py``)
2. Define a ``register(mcp)`` function inside it
3. Import and call it here
"""

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


def register_all_tools(mcp):
    """Register every tool group onto the given MCP server instance."""
    email.register(mcp)
    messaging.register(mcp)
    calendar.register(mcp)
    code.register(mcp)
    files.register(mcp)
    browser.register(mcp)
    system.register(mcp)
    memory.register(mcp)
