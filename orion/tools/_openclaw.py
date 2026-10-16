"""
Helper for declaring tools that OpenClaw executes.

OpenClaw accepts natural-language instructions, so an OpenClaw tool is just a
typed input model plus a ``render`` function that turns a validated payload
into the instruction text.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from bridge import get_openclaw_client
from orion.core.models import ToolSafetyLevel
from orion.core.registry import ToolDefinition
from orion.openclaw_setup import agent_for


def openclaw_tool(
    *,
    name: str,
    description: str,
    input_model: type[BaseModel],
    safety_level: ToolSafetyLevel,
    render: Callable[[Any], str],
    action: str,
    describe: Callable[[Any], str] | None = None,
) -> ToolDefinition[Any]:
    """Declare a tool whose handler sends ``render(payload)`` to OpenClaw.

    The instruction goes to the least-privilege OpenClaw agent for the tool's
    safety level when scoped agents are enabled.
    """

    async def handler(payload: Any) -> dict[str, str]:
        from orion.config import config

        agent = agent_for(safety_level, config)
        result = await get_openclaw_client().send_task(render(payload), agent=agent)
        if result["status"] != "success":
            raise RuntimeError(result["result"])
        return {"message": result["result"]}

    return ToolDefinition(
        name=name,
        description=description,
        input_model=input_model,
        handler=handler,
        safety_level=safety_level,
        action=action,
        describe=describe,
    )
