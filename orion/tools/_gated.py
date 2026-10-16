"""
Shared path for voice tools that must go through the approval gate.

Every side-effectful MCP tool calls ``run_gated`` so that execution, approval
and the spoken outcome are handled identically — and a failure can never be
reported to the user as success.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from orion.core.models import Task, TaskStatus

if TYPE_CHECKING:
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


async def run_gated(
    runtime: Runtime, tool_name: str, user_intent: str, action: str, **tool_args: Any
) -> str:
    """Run a registered tool under the approval gate and describe the outcome."""
    task = await runtime.run_tool(tool_name, user_intent, **tool_args)
    return describe_outcome(task, action)
