"""
File tools — read, write and search files via OpenClaw.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from orion.core.models import ToolSafetyLevel
from orion.core.registry import ToolDefinition
from orion.tools._openclaw import openclaw_tool
from orion.tools._safe import Line, q


class ReadFileInput(BaseModel):
    path: Line = Field(description="Absolute or relative file path.")


class WriteFileInput(BaseModel):
    path: Line = Field(description="File path to write to.")
    content: str = Field(description="Content to write into the file.")


class SearchFilesInput(BaseModel):
    query: Line = Field(description="Filename, extension or content pattern to search for.")
    directory: Line = Field(".", description="Directory to search in.")


TOOLS: list[ToolDefinition[Any]] = [
    openclaw_tool(
        name="read_file",
        description="Read the contents of a file.",
        input_model=ReadFileInput,
        safety_level=ToolSafetyLevel.READ_ONLY,
        render=lambda p: (
            f"Read the contents of the file at {q(p.path)} and return a summary of what's in it."
        ),
        action="Reading the file",
    ),
    openclaw_tool(
        name="write_file",
        description=(
            "Write content to a file, creating it if it doesn't exist. "
            "Requires approval before execution."
        ),
        input_model=WriteFileInput,
        safety_level=ToolSafetyLevel.DESTRUCTIVE,
        render=lambda p: f"Write the content {q(p.content)} to the file at {q(p.path)}.",
        action="Writing the file",
        describe=lambda p: f"Write file: {p.path}",
    ),
    openclaw_tool(
        name="search_files",
        description="Search for files matching a query in a directory.",
        input_model=SearchFilesInput,
        safety_level=ToolSafetyLevel.READ_ONLY,
        render=lambda p: (
            f"Search for files matching {q(p.query)} in the directory {q(p.directory)}. "
            "List what you find."
        ),
        action="The file search",
    ),
]
