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
        Requires approval before execution.

        Args:
            path: File path to write to.
            content: Content to write into the file.
        """
        from orion.core.models import TaskStatus
        from orion.core.runtime import run_runtime_write_file

        task = await run_runtime_write_file(path=path, content=content)
        if task.status == TaskStatus.AWAITING_APPROVAL:
            return (
                f"Writing to '{path}' requires your approval. "
                "Please approve via the Orion API or say 'approve' to proceed."
            )
        if task.steps and task.steps[-1].tool_result:
            return task.steps[-1].tool_result.output.get("message", "File written, sir.")
        return "File written, sir."

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
