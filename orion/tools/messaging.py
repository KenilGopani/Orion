"""
Messaging tools — WhatsApp, Telegram and Slack via OpenClaw skills.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from orion.core.models import ToolSafetyLevel
from orion.core.registry import ToolDefinition
from orion.tools._openclaw import openclaw_tool
from orion.tools._safe import Line, q


class SendMessageInput(BaseModel):
    recipient: Line = Field(description="Contact name, username or phone number.")
    message: str = Field(description="The message to send.")


class SendSlackInput(BaseModel):
    channel: Line = Field(description='Slack channel or user, e.g. "#general" or "@username".')
    message: str = Field(description="The message to send.")


def _preview(text: str) -> str:
    return text if len(text) <= 80 else text[:79] + "…"


TOOLS: list[ToolDefinition[Any]] = [
    openclaw_tool(
        name="send_whatsapp",
        description="Send a WhatsApp message to someone. Requires approval before execution.",
        input_model=SendMessageInput,
        safety_level=ToolSafetyLevel.EXTERNAL_SIDE_EFFECT,
        render=lambda p: f"Send a WhatsApp message to {q(p.recipient)} saying {q(p.message)}.",
        action="The WhatsApp message",
        describe=lambda p: f"WhatsApp {p.recipient}: {_preview(p.message)}",
    ),
    openclaw_tool(
        name="send_telegram",
        description="Send a Telegram message to someone. Requires approval before execution.",
        input_model=SendMessageInput,
        safety_level=ToolSafetyLevel.EXTERNAL_SIDE_EFFECT,
        render=lambda p: f"Send a Telegram message to {q(p.recipient)} saying {q(p.message)}.",
        action="The Telegram message",
        describe=lambda p: f"Telegram {p.recipient}: {_preview(p.message)}",
    ),
    openclaw_tool(
        name="send_slack",
        description="Send a message to a Slack channel. Requires approval before execution.",
        input_model=SendSlackInput,
        safety_level=ToolSafetyLevel.EXTERNAL_SIDE_EFFECT,
        render=lambda p: f"Send a Slack message to {q(p.channel)} saying {q(p.message)}.",
        action="The Slack message",
        describe=lambda p: f"Slack {p.channel}: {_preview(p.message)}",
    ),
]
