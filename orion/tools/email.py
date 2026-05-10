"""
Email tools — delegate all execution to OpenClaw.

The MCP tool wrappers translate structured LLM calls into
natural-language instructions that OpenClaw can understand and execute
via its installed email skills (Gmail, Outlook, etc.).
"""

from __future__ import annotations

from bridge import openclaw_client
from orion.core.models import TaskStatus
from orion.core.runtime import run_runtime_send_email


def register(mcp):

    @mcp.tool()
    async def check_email(
        count: int = 10,
        filter: str = "unread",
        summarize: bool = True,
    ) -> str:
        """
        Check the user's email inbox.

        Args:
            count: Number of emails to retrieve (default 10).
            filter: Filter type — "unread", "all", "starred", or "important".
            summarize: If true, summarise what's urgent. Otherwise list subjects.
        """
        task = f"Check my {filter} emails, get the last {count}."
        if summarize:
            task += " Summarize what's urgent or important."
        else:
            task += " List the subject lines and senders."
        result = await openclaw_client.send_task(task)
        return result["result"]

    @mcp.tool()
    async def send_email(to: str, subject: str, body: str) -> str:
        """
        Send an email to someone.

        Args:
            to: Recipient email address or name.
            subject: Email subject line.
            body: Email body content.
        """
        runtime_task = await run_runtime_send_email(to=to, subject=subject, body=body)
        if runtime_task.status == TaskStatus.AWAITING_APPROVAL:
            return (
                "Email requires approval before execution. "
                f"Approve task via API: POST /tasks/{runtime_task.id}/approve"
            )
        if runtime_task.status == TaskStatus.SUCCEEDED and runtime_task.steps:
            result = runtime_task.steps[-1].tool_result
            if result and result.output.get("message"):
                return str(result.output["message"])
            return "Email task completed successfully."
        if runtime_task.error:
            return f"Email task failed: {runtime_task.error}"
        return f"Email task ended with status {runtime_task.status}."

    @mcp.tool()
    async def summarize_inbox() -> str:
        """Get a brief digest of the user's email inbox — what needs attention."""
        task = (
            "Summarize my email inbox. Focus on what's urgent, "
            "what needs a reply, and anything time-sensitive. "
            "Keep it brief — I'm listening, not reading."
        )
        result = await openclaw_client.send_task(task)
        return result["result"]
