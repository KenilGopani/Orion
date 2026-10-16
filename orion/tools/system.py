"""
System tools — time, system info and shell commands.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from orion.core.models import ToolSafetyLevel
from orion.core.registry import ToolDefinition
from orion.tools._openclaw import openclaw_tool


class NoInput(BaseModel):
    pass


class RunCommandInput(BaseModel):
    command: str = Field(description="The shell command to execute.")


def _get_time(_: NoInput) -> dict[str, str]:
    now = datetime.now()
    utc_now = datetime.now(timezone.utc)
    return {
        "message": (
            f"The current local time is {now.strftime('%I:%M %p on %A, %B %d, %Y')}. "
            f"UTC time is {utc_now.strftime('%H:%M')}."
        )
    }


TOOLS: list[ToolDefinition[Any]] = [
    ToolDefinition(
        name="get_time",
        description="Get the current date and time.",
        input_model=NoInput,
        handler=_get_time,
        safety_level=ToolSafetyLevel.READ_ONLY,
        action="Checking the time",
    ),
    openclaw_tool(
        name="get_system_info",
        description="Get information about the user's system — OS, hardware, disk space, etc.",
        input_model=NoInput,
        safety_level=ToolSafetyLevel.READ_ONLY,
        render=lambda p: (
            "Get system information: operating system, CPU, memory usage, "
            "disk space, and uptime. Summarize it briefly."
        ),
        action="The system check",
    ),
    openclaw_tool(
        name="run_command",
        description="Run a shell command on the user's system. Requires approval before execution.",
        input_model=RunCommandInput,
        safety_level=ToolSafetyLevel.DESTRUCTIVE,
        render=lambda p: f"Run the following shell command and tell me the output: {p.command}",
        action="The command",
        describe=lambda p: f"Run command: {p.command[:80]}",
    ),
]
