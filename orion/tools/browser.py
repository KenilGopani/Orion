"""
Browser tools — open URLs, search the web, take screenshots via OpenClaw.
"""

from __future__ import annotations
from bridge import get_openclaw_client


def register(mcp):

    @mcp.tool()
    async def open_url(url: str) -> str:
        """
        Open a URL in the system's web browser.

        Args:
            url: The URL to open.
        """
        task = f"Open the following URL in the web browser: {url}"
        result = await get_openclaw_client().send_task(task)
        return result["result"]

    @mcp.tool()
    async def search_web(query: str) -> str:
        """
        Search the web for a query and return a summary of results.

        Args:
            query: The search query.
        """
        task = f"Search the web for: {query}. Summarize the top results briefly."
        result = await get_openclaw_client().send_task(task)
        return result["result"]

    @mcp.tool()
    async def take_screenshot() -> str:
        """Take a screenshot of the current screen."""
        task = "Take a screenshot of the current screen and describe what's visible."
        result = await get_openclaw_client().send_task(task)
        return result["result"]
