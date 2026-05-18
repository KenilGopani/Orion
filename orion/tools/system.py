"""
System tools — time, system info, shell commands via OpenClaw.
"""

from __future__ import annotations
from datetime import datetime, timezone
from bridge import get_openclaw_client


def register(mcp):

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

        Args:
            command: The shell command to execute.
        """
        task = f"Run the following shell command and tell me the output: {command}"
        result = await get_openclaw_client().send_task(task)
        return result["result"]
