"""
Email tools — executed by OpenClaw's installed email skills (Gmail, Outlook, …).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from orion.core.models import ToolSafetyLevel
from orion.core.registry import ToolDefinition
from orion.tools._openclaw import openclaw_tool


class CheckEmailInput(BaseModel):
    count: int = Field(10, description="Number of emails to retrieve.")
    filter: str = Field("unread", description='Filter: "unread", "all", "starred" or "important".')
    summarize: bool = Field(True, description="Summarise what's urgent; otherwise list subjects.")


class SendEmailInput(BaseModel):
    to: str = Field(description="Recipient email address or name.")
    subject: str = Field(description="Email subject line.")
    body: str = Field(description="Email body content.")


class NoInput(BaseModel):
    pass


def _render_check_email(p: CheckEmailInput) -> str:
    task = f"Check my {p.filter} emails, get the last {p.count}."
    if p.summarize:
        return task + " Summarize what's urgent or important."
    return task + " List the subject lines and senders."


TOOLS: list[ToolDefinition[Any]] = [
    openclaw_tool(
        name="check_email",
        description="Check the user's email inbox.",
        input_model=CheckEmailInput,
        safety_level=ToolSafetyLevel.READ_ONLY,
        render=_render_check_email,
        action="Checking your email",
    ),
    openclaw_tool(
        name="send_email",
        description="Send an email to someone. Requires approval before execution.",
        input_model=SendEmailInput,
        safety_level=ToolSafetyLevel.EXTERNAL_SIDE_EFFECT,
        render=lambda p: f"Send an email to {p.to} with subject '{p.subject}' and body: {p.body}",
        action="The email",
        describe=lambda p: f"Send email to {p.to}: {p.subject}",
    ),
    openclaw_tool(
        name="summarize_inbox",
        description="Get a brief digest of the user's email inbox — what needs attention.",
        input_model=NoInput,
        safety_level=ToolSafetyLevel.READ_ONLY,
        render=lambda p: (
            "Summarize my email inbox. Focus on what's urgent, "
            "what needs a reply, and anything time-sensitive. "
            "Keep it brief — I'm listening, not reading."
        ),
        action="The inbox summary",
    ),
]
