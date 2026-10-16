"""
Orion's tools — one declaration per capability.

Each module here exports ``TOOLS``: a list of ``ToolDefinition``s giving the
tool's name, typed input, safety level and handler. ``build_registry()`` puts
them all in the engine's registry, and the voice LLM's MCP surface is
generated from that registry (``orion.tools._mcp``), so every voice call runs
through the engine and its approval gate.

To add a capability, declare it in the right module (or a new one listed in
``all_tools``). There is nothing else to wire up.
"""

from __future__ import annotations

from typing import Any

from orion.core.registry import ToolDefinition
from orion.tools import browser, calendar, code, email, files, memory, messaging, system


def all_tools() -> list[ToolDefinition[Any]]:
    """Every declared tool, in a stable order."""
    return [
        tool
        for module in (email, messaging, calendar, code, files, browser, system, memory)
        for tool in module.TOOLS
    ]
