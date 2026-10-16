"""
Code tools — create projects, run snippets and open the editor via OpenClaw.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from orion.core.models import ToolSafetyLevel
from orion.core.registry import ToolDefinition
from orion.tools._openclaw import openclaw_tool
from orion.tools._safe import Line, q


class CreateProjectInput(BaseModel):
    name: Line = Field(description="Project name.")
    language: Line = Field("python", description='Programming language, e.g. "python" or "typescript".')
    framework: Line = Field("", description='Framework, e.g. "fastapi" or "nextjs" (optional).')
    path: Line = Field("", description="Directory to create it in (optional; defaults to the dev folder).")


class RunCodeInput(BaseModel):
    code: str = Field(description="The code to execute.")
    language: Line = Field("python", description="Programming language of the code.")


class OpenEditorInput(BaseModel):
    path: Line = Field(description="File or directory path to open.")


def _render_create_project(p: CreateProjectInput) -> str:
    task = f"Create a new {q(p.language)} project called {q(p.name)}"
    if p.framework:
        task += f" using the {q(p.framework)} framework"
    if p.path:
        task += f" in the directory {q(p.path)}"
    return task + ". Set up the standard project structure, dependencies, and a basic starter file."


TOOLS: list[ToolDefinition[Any]] = [
    openclaw_tool(
        name="create_project",
        description=(
            "Create a new code project. Requires approval before execution, "
            "since installing dependencies runs third-party code."
        ),
        input_model=CreateProjectInput,
        # Dependency installation executes package install scripts.
        safety_level=ToolSafetyLevel.DESTRUCTIVE,
        render=_render_create_project,
        action="Creating the project",
        describe=lambda p: f"Create {p.language} project: {p.name}",
    ),
    openclaw_tool(
        name="run_code",
        description="Run a code snippet and return the output. Requires approval before execution.",
        input_model=RunCodeInput,
        safety_level=ToolSafetyLevel.DESTRUCTIVE,
        render=lambda p: f"Run the following {q(p.language)} code and tell me the output: {q(p.code)}",
        action="The code",
        describe=lambda p: f"Run {p.language} code ({len(p.code.splitlines())} lines)",
    ),
    openclaw_tool(
        name="open_editor",
        description="Open a file or project in the default code editor.",
        input_model=OpenEditorInput,
        safety_level=ToolSafetyLevel.LOW_RISK,
        render=lambda p: f"Open {q(p.path)} in the default code editor (VS Code or similar).",
        action="Opening the editor",
    ),
]
