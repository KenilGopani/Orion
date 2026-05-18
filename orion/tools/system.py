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
        Requires approval before execution.

        Args:
            command: The shell command to execute.
        """
        from orion.core.models import TaskStatus
        from orion.core.runtime import run_runtime_run_command

        task = await run_runtime_run_command(command=command)
        if task.status == TaskStatus.AWAITING_APPROVAL:
            return (
                f"Running '{command}' requires your approval. "
                "Please approve via the Orion API or say 'approve' to proceed."
            )
        if task.steps and task.steps[-1].tool_result:
            return task.steps[-1].tool_result.output.get("message", "Command executed, sir.")
        return "Command executed, sir."
