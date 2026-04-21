"""
Messaging tools — WhatsApp, Telegram, Slack via OpenClaw.

Each function translates a structured tool call into a natural-language
task string for OpenClaw, which has skills installed for each platform.
"""

from __future__ import annotations
from bridge import openclaw_client


def register(mcp):

    @mcp.tool()
    async def send_whatsapp(recipient: str, message: str) -> str:
        """
        Send a WhatsApp message to someone.

        Args:
            recipient: Contact name or phone number.
            message: The message to send.
        """
        task = f"Send a WhatsApp message to {recipient}: {message}"
        result = await openclaw_client.send_task(task)
        return result["result"]

    @mcp.tool()
    async def send_telegram(recipient: str, message: str) -> str:
        """
        Send a Telegram message to someone.

        Args:
            recipient: Contact name or username.
            message: The message to send.
        """
        task = f"Send a Telegram message to {recipient}: {message}"
        result = await openclaw_client.send_task(task)
        return result["result"]

    @mcp.tool()
    async def send_slack(channel: str, message: str) -> str:
        """
        Send a message to a Slack channel.

        Args:
            channel: Slack channel name (e.g. "#general" or "@username").
            message: The message to send.
        """
        task = f"Send a Slack message to {channel}: {message}"
        result = await openclaw_client.send_task(task)
        return result["result"]
