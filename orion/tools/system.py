"""
System tools — time, system info, shell commands via OpenClaw.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from bridge import get_openclaw_client
from orion.tools._gated import run_gated

if TYPE_CHECKING:
    from orion.core.runtime import Runtime


def register(mcp, runtime: Runtime) -> None:

    @mcp.tool()
    async def get_time() -> str:
        """Get the current date and time."""
        now = datetime.now()
        utc_now = datetime.now(timezone.utc)
        return (
            f"The current local time is {now.strftime('%I:%M %p on %A, %B %d, %Y')}. "
            f"UTC time is {utc_now.strftime('%H:%M')}."
        )

    @mcp.tool()
    async def get_system_info() -> str:
        """Get information about the user's system — OS, hardware, disk space, etc."""
        task = (
            "Get system information: operating system, CPU, memory usage, "
            "disk space, and uptime. Summarize it briefly."
        )
        result = await get_openclaw_client().send_task(task)
        return result["result"]

    @mcp.tool()
    async def run_command(command: str) -> str:
        """
        Run a shell command on the user's system.
        Requires approval before execution.

        Args:
            command: The shell command to execute.
        """
        return await run_gated(
            runtime,
            "openclaw_run_command",
            f"Run command: {command[:80]}",
            "The command",
            command=command,
        )
