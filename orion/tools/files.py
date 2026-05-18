"""
File tools — read, write, and search files via OpenClaw.
"""

from __future__ import annotations
from bridge import get_openclaw_client


def register(mcp):

    @mcp.tool()
    async def read_file(path: str) -> str:
        """
        Read the contents of a file.

        Args:
            path: Absolute or relative file path.
        """
        task = f"Read the contents of the file at '{path}' and return a summary of what's in it."
        result = await get_openclaw_client().send_task(task)
        return result["result"]

    @mcp.tool()
    async def write_file(path: str, content: str) -> str:
        """
        Write content to a file, creating it if it doesn't exist.

        Args:
            path: File path to write to.
            content: Content to write into the file.
        """
        task = f"Write the following content to the file at '{path}':\n{content}"
        result = await get_openclaw_client().send_task(task)
        return result["result"]

    @mcp.tool()
    async def search_files(query: str, directory: str = ".") -> str:
        """
        Search for files matching a query in a directory.

        Args:
            query: Search term — can be a filename, extension, or content pattern.
            directory: Directory to search in (default: current directory).
        """
        task = f"Search for files matching '{query}' in the directory '{directory}'. List what you find."
        result = await get_openclaw_client().send_task(task)
        return result["result"]
