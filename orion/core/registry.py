from __future__ import annotations

from collections.abc import Awaitable
from collections.abc import Callable
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from orion.core.models import ToolSafetyLevel

#: The Pydantic model a tool's handler accepts. Parameterising ``ToolDefinition``
#: on this keeps ``input_model`` and ``handler`` provably in agreement — a
#: handler taking ``SendEmailInput`` can only be paired with that input model.
TInput = TypeVar("TInput", bound=BaseModel)


class ToolDefinition(BaseModel, Generic[TInput]):
    name: str
    description: str
    input_model: type[TInput]
    handler: Callable[[TInput], dict[str, Any] | Awaitable[dict[str, Any]]]
    safety_level: ToolSafetyLevel

    @property
    def requires_approval(self) -> bool:
        return self.safety_level in {
            ToolSafetyLevel.EXTERNAL_SIDE_EFFECT,
            ToolSafetyLevel.DESTRUCTIVE,
        }


class ToolRegistry:
    """Holds tools of differing input types, so it stores them erased to Any."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition[Any]] = {}

    def register(self, tool: ToolDefinition[Any]) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool {tool.name} is already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition[Any]:
        tool = self._tools.get(name)
        if not tool:
            raise KeyError(f"Tool {name} is not registered")
        return tool

    def list_tools(self) -> list[ToolDefinition[Any]]:
        return list(self._tools.values())
