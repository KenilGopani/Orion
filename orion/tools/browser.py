"""
Browser tools — open URLs, search the web and take screenshots via OpenClaw.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from orion.core.models import ToolSafetyLevel
from orion.core.registry import ToolDefinition
from orion.tools._openclaw import openclaw_tool
from orion.tools._safe import HttpUrl, Line, q


class OpenUrlInput(BaseModel):
    url: HttpUrl = Field(description="The http(s) URL to open.")


class SearchWebInput(BaseModel):
    query: Line = Field(description="The search query.")


class NoInput(BaseModel):
    pass


TOOLS: list[ToolDefinition[Any]] = [
    openclaw_tool(
        name="open_url",
        description="Open a URL in the system's web browser.",
        input_model=OpenUrlInput,
        safety_level=ToolSafetyLevel.LOW_RISK,
        render=lambda p: f"Open the URL {q(p.url)} in the web browser.",
        action="Opening the link",
    ),
    openclaw_tool(
        name="search_web",
        description="Search the web for a query and return a summary of results.",
        input_model=SearchWebInput,
        safety_level=ToolSafetyLevel.READ_ONLY,
        render=lambda p: f"Search the web for {q(p.query)}. Summarize the top results briefly.",
        action="The web search",
    ),
    openclaw_tool(
        name="take_screenshot",
        description="Take a screenshot of the current screen.",
        input_model=NoInput,
        safety_level=ToolSafetyLevel.READ_ONLY,
        render=lambda p: "Take a screenshot of the current screen and describe what's visible.",
        action="The screenshot",
    ),
]
