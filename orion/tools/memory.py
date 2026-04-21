"""
Memory tools — remember facts, recall knowledge, forget things via OpenClaw.

OpenClaw's memory skill provides persistent cross-session storage,
so Orion can remember preferences, facts, and context over time.
"""

from __future__ import annotations
from bridge import openclaw_client


def register(mcp):

    @mcp.tool()
    async def remember_this(fact: str) -> str:
        """
        Store a fact or piece of information for future recall.

        Args:
            fact: The information to remember (e.g. "My standup is at 10am every weekday").
        """
        task = f"Remember the following for future reference: {fact}"
        result = await openclaw_client.send_task(task)
        return result["result"]

    @mcp.tool()
    async def what_do_i_know_about(topic: str) -> str:
        """
        Recall stored information about a topic.

        Args:
            topic: The topic to search memory for (e.g. "standup time", "Priya's email").
        """
        task = f"What do you know about: {topic}? Search your memory and tell me."
        result = await openclaw_client.send_task(task)
        return result["result"]

    @mcp.tool()
    async def forget(topic: str) -> str:
        """
        Remove stored information about a topic from memory.

        Args:
            topic: The topic to forget.
        """
        task = f"Forget everything stored about: {topic}"
        result = await openclaw_client.send_task(task)
        return result["result"]
