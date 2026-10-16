"""
Messaging tools — WhatsApp, Telegram, Slack via OpenClaw.

Each function translates a structured tool call into a natural-language
task string for OpenClaw, which has skills installed for each platform.
"""

from __future__ import annotations

from orion.tools._gated import run_gated


def register(mcp):

    @mcp.tool()
    async def send_whatsapp(recipient: str, message: str) -> str:
        """
        Send a WhatsApp message to someone.

        Args:
            recipient: Contact name or phone number.
            message: The message to send.
        """
        return await run_gated(
            "openclaw_send_whatsapp",
            f"WhatsApp {recipient}: {message[:80]}",
            "The WhatsApp message",
            recipient=recipient,
            message=message,
        )

    @mcp.tool()
    async def send_telegram(recipient: str, message: str) -> str:
        """
        Send a Telegram message to someone.
        Requires approval before execution.

        Args:
            recipient: Contact name or username.
            message: The message to send.
        """
        return await run_gated(
            "openclaw_send_telegram",
            f"Telegram {recipient}: {message[:80]}",
            "The Telegram message",
            recipient=recipient,
            message=message,
        )

    @mcp.tool()
    async def send_slack(channel: str, message: str) -> str:
        """
        Send a message to a Slack channel.
        Requires approval before execution.

        Args:
            channel: Slack channel name (e.g. "#general" or "@username").
            message: The message to send.
        """
        return await run_gated(
            "openclaw_send_slack",
            f"Slack {channel}: {message[:80]}",
            "The Slack message",
            channel=channel,
            message=message,
        )
