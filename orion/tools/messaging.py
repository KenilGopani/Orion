"""
Messaging tools — WhatsApp, Telegram, Slack via OpenClaw.

Each function translates a structured tool call into a natural-language
task string for OpenClaw, which has skills installed for each platform.
"""

from __future__ import annotations

from bridge import get_openclaw_client
from orion.core.models import TaskStatus
from orion.core.runtime import run_runtime_send_whatsapp


def register(mcp):

    @mcp.tool()
    async def send_whatsapp(recipient: str, message: str) -> str:
        """
        Send a WhatsApp message to someone.

        Args:
            recipient: Contact name or phone number.
            message: The message to send.
        """
        runtime_task = await run_runtime_send_whatsapp(recipient=recipient, message=message)
        if runtime_task.status == TaskStatus.AWAITING_APPROVAL:
            return (
                "WhatsApp send requires approval before execution. "
                f"Approve task via API: POST /tasks/{runtime_task.id}/approve"
            )
        if runtime_task.status == TaskStatus.SUCCEEDED and runtime_task.steps:
            result = runtime_task.steps[-1].tool_result
            if result and result.output.get("message"):
                return str(result.output["message"])
            return "WhatsApp task completed successfully."
        if runtime_task.error:
            return f"WhatsApp task failed: {runtime_task.error}"
        return f"WhatsApp task ended with status {runtime_task.status}."

    @mcp.tool()
    async def send_telegram(recipient: str, message: str) -> str:
        """
        Send a Telegram message to someone.
        Requires approval before execution.

        Args:
            recipient: Contact name or username.
            message: The message to send.
        """
        from orion.core.runtime import run_runtime_send_telegram

        runtime_task = await run_runtime_send_telegram(recipient=recipient, message=message)
        if runtime_task.status == TaskStatus.AWAITING_APPROVAL:
            return (
                "Telegram send requires approval before execution. "
                f"Approve task via API: POST /tasks/{runtime_task.id}/approve"
            )
        if runtime_task.status == TaskStatus.SUCCEEDED and runtime_task.steps:
            result = runtime_task.steps[-1].tool_result
            if result and result.output.get("message"):
                return str(result.output["message"])
            return "Telegram message sent, sir."
        if runtime_task.error:
            return f"Telegram task failed: {runtime_task.error}"
        return f"Telegram task ended with status {runtime_task.status}."

    @mcp.tool()
    async def send_slack(channel: str, message: str) -> str:
        """
        Send a message to a Slack channel.
        Requires approval before execution.

        Args:
            channel: Slack channel name (e.g. "#general" or "@username").
            message: The message to send.
        """
        from orion.core.runtime import run_runtime_send_slack

        runtime_task = await run_runtime_send_slack(channel=channel, message=message)
        if runtime_task.status == TaskStatus.AWAITING_APPROVAL:
            return (
                "Slack send requires approval before execution. "
                f"Approve task via API: POST /tasks/{runtime_task.id}/approve"
            )
        if runtime_task.status == TaskStatus.SUCCEEDED and runtime_task.steps:
            result = runtime_task.steps[-1].tool_result
            if result and result.output.get("message"):
                return str(result.output["message"])
            return "Slack message sent, sir."
        if runtime_task.error:
            return f"Slack task failed: {runtime_task.error}"
        return f"Slack task ended with status {runtime_task.status}."
