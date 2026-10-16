"""
Email tools — delegate all execution to OpenClaw.

The MCP tool wrappers translate structured LLM calls into
natural-language instructions that OpenClaw can understand and execute
via its installed email skills (Gmail, Outlook, etc.).
"""

from __future__ import annotations

from bridge import get_openclaw_client
from orion.tools._gated import run_gated


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
        result = await get_openclaw_client().send_task(task)
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
        return await run_gated(
            "openclaw_send_email",
            f"Send email to {to} with subject {subject}",
            "The email",
            to=to,
            subject=subject,
            body=body,
        )

    @mcp.tool()
    async def summarize_inbox() -> str:
        """Get a brief digest of the user's email inbox — what needs attention."""
        task = (
            "Summarize my email inbox. Focus on what's urgent, "
            "what needs a reply, and anything time-sensitive. "
            "Keep it brief — I'm listening, not reading."
        )
        result = await get_openclaw_client().send_task(task)
        return result["result"]
