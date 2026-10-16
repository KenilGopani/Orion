"""
Evals and benchmarks: measure Orion instead of guessing.

``make eval``  — tool-selection accuracy for the configured LLM provider
``make bench`` — per-stage latency (STT, LLM, TTS) and memory on this machine
"""

from __future__ import annotations

from orion.core.models import ToolSafetyLevel
from orion.evals.llm import ToolSpec


async def voice_tools() -> tuple[list[ToolSpec], dict[str, ToolSafetyLevel]]:
    """The tools exactly as the voice LLM sees them, plus each one's safety level.

    Built from the generated MCP surface itself, so the eval can't drift from
    what runs in production.
    """
    from orion.app import build_mcp
    from orion.core.runtime import build_runtime

    runtime = build_runtime()
    specs = [
        ToolSpec(t.name, t.description or "", t.inputSchema)
        for t in await build_mcp(runtime).list_tools()
    ]
    safety = {t.name: t.safety_level for t in runtime.registry.list_tools()}
    return specs, safety


def voice_system_prompt() -> str:
    """Orion's persona prompt, without the user's stored memories."""
    from orion.persona import get_system_prompt

    return get_system_prompt(include_memories=False)
