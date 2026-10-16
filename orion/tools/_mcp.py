"""
The voice LLM's MCP surface, generated from the tool registry.

Every registry tool marked ``voice`` becomes an MCP tool whose signature and
argument descriptions come from its Pydantic input model. Each call runs
through ``Runtime.run_tool`` — so through the engine and the approval gate —
and is answered with one speakable sentence. There is no other path from the
voice LLM to OpenClaw.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import BaseModel, Field

from orion.core.models import Task, TaskStatus
from orion.core.registry import ToolDefinition

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from orion.core.runtime import Runtime


def describe_outcome(task: Task, action: str) -> str:
    """Turn a finished (or paused) task into a short, speakable sentence."""
    if task.status == TaskStatus.AWAITING_APPROVAL:
        return f"{action} is ready and waiting for your approval on the Orion dashboard."
    if task.status == TaskStatus.SUCCEEDED:
        result = task.steps[-1].tool_result if task.steps else None
        if result and result.output.get("message"):
            return str(result.output["message"])
        return f"{action} done."
    if task.status == TaskStatus.FAILED:
        return f"{action} didn't go through. {task.error or ''}".strip()
    return f"{action} is {task.status.value.lower().replace('_', ' ')}."


def _signature(model: type[BaseModel]) -> inspect.Signature:
    """A keyword-only signature mirroring ``model``'s fields.

    FastMCP builds each tool's JSON schema from the function signature, so
    field types, defaults and descriptions carry straight through to the LLM.
    """
    params = []
    for name, field in model.model_fields.items():
        annotation: Any = field.annotation
        if field.description:
            annotation = Annotated[annotation, Field(description=field.description)]
        default = inspect.Parameter.empty if field.is_required() else field.default
        params.append(
            inspect.Parameter(name, inspect.Parameter.KEYWORD_ONLY, default=default, annotation=annotation)
        )
    return inspect.Signature(params, return_annotation=str)


def _voice_tool(runtime: Runtime, tool: ToolDefinition[Any]) -> Any:
    action = tool.action or tool.name.replace("_", " ").capitalize()

    async def call(**kwargs: Any) -> str:
        intent = tool.intent_for(tool.input_model(**kwargs))
        task = await runtime.run_tool(tool.name, intent, **kwargs)
        return describe_outcome(task, action)

    call.__name__ = tool.name
    call.__doc__ = tool.description
    call.__signature__ = _signature(tool.input_model)  # type: ignore[attr-defined]
    return call


def expose_tools(mcp: FastMCP, runtime: Runtime) -> None:
    """Register every voice-facing registry tool on ``mcp``."""
    for tool in runtime.registry.list_tools():
        if tool.voice:
            mcp.add_tool(_voice_tool(runtime, tool), name=tool.name, description=tool.description)
