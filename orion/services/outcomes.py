"""
Approval outcomes: what happened to an action after the user decided on it.

When a task that waited for approval finishes (approved and done, approved but
failed, or rejected), ``outcome_for`` turns the engine event into a short
update the voice agent can speak. Tasks that never needed approval produce
nothing; the user already heard their result in the same turn.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from orion.core.models import RuntimeEvent

if TYPE_CHECKING:
    from orion.core.runtime import Runtime

TERMINAL_EVENTS = {"task_succeeded": "succeeded", "task_failed": "failed", "task_rejected": "rejected"}

# Spoken updates are short; OpenClaw's own summary is already capped at ~800 chars.
_DETAIL_MAX = 240


def _clip(text: str) -> str:
    text = text.strip()
    return text if len(text) <= _DETAIL_MAX else text[: _DETAIL_MAX - 1].rstrip() + "…"


def outcome_for(event: RuntimeEvent, runtime: Runtime) -> dict[str, Any] | None:
    """The spoken update for ``event``, or None if it isn't an approval outcome."""
    outcome = TERMINAL_EVENTS.get(event.event_type)
    if outcome is None:
        return None
    approvals = runtime.store.list_approval_requests(event.task_id)
    task = runtime.store.get_task(event.task_id)
    if not approvals or task is None:
        return None

    step = next((s for s in task.steps if s.id == approvals[-1].step_id), None)
    action = "The action"
    if step and step.planned_tool_name:
        try:
            tool = runtime.registry.get(step.planned_tool_name)
            action = tool.action or tool.name.replace("_", " ").capitalize()
        except KeyError:
            pass

    if outcome == "succeeded":
        detail = step.tool_result.output.get("message", "") if step and step.tool_result else ""
        speech = f"{action} you approved went through."
        if detail:
            speech += f" {_clip(str(detail))}"
    elif outcome == "failed":
        speech = f"{action} you approved didn't go through."
        if task.error:
            speech += f" {_clip(task.error)}"
    else:
        speech = f"Okay, I didn't go ahead with {action[0].lower() + action[1:]}."

    return {
        "task_id": task.id,
        "outcome": outcome,
        "user_intent": task.user_intent,
        "speech": speech,
    }
