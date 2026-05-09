from __future__ import annotations

from collections.abc import Awaitable
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from orion.core.models import ToolSafetyLevel


class ToolDefinition(BaseModel):
    name: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[[BaseModel], dict[str, Any] | Awaitable[dict[str, Any]]]
    safety_level: ToolSafetyLevel

    @property
    def requires_approval(self) -> bool:
        return self.safety_level in {
            ToolSafetyLevel.EXTERNAL_SIDE_EFFECT,
            ToolSafetyLevel.DESTRUCTIVE,
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool {tool.name} is already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition:
        tool = self._tools.get(name)
        if not tool:
            raise KeyError(f"Tool {name} is not registered")
        return tool

    def list_tools(self) -> list[ToolDefinition]:
        return list(self._tools.values())
