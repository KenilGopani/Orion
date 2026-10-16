"""
Code tools — create projects, run scripts, open editor via OpenClaw.
"""

from __future__ import annotations
from bridge import get_openclaw_client
from orion.tools._gated import run_gated


def register(mcp):

    @mcp.tool()
    async def create_project(
        name: str,
        language: str = "python",
        framework: str = "",
        path: str = "",
    ) -> str:
        """
        Create a new code project.

        Args:
            name: Project name.
            language: Programming language (e.g. "python", "javascript", "typescript").
            framework: Framework to use (e.g. "fastapi", "nextjs", "express"). Optional.
            path: Directory path to create the project in. Optional — defaults to user's dev folder.
        """
        task = f"Create a new {language} project called '{name}'"
        if framework:
            task += f" using the {framework} framework"
        if path:
            task += f" in the directory {path}"
        task += ". Set up the standard project structure, dependencies, and a basic starter file."
        result = await get_openclaw_client().send_task(task)
        return result["result"]

    @mcp.tool()
    async def run_code(code: str, language: str = "python") -> str:
        """
        Run a code snippet and return the output.
        Requires approval before execution.

        Args:
            code: The code to execute.
            language: Programming language of the code.
        """
        return await run_gated(
            "openclaw_run_code",
            f"Run {language} code ({len(code.splitlines())} lines)",
            "The code",
            code=code,
            language=language,
        )

    @mcp.tool()
    async def open_editor(path: str) -> str:
        """
        Open a file or project in the default code editor.

        Args:
            path: File or directory path to open.
        """
        task = f"Open '{path}' in the default code editor (VS Code or similar)."
        result = await get_openclaw_client().send_task(task)
        return result["result"]
