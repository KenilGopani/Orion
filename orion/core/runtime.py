from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from bridge import get_openclaw_client
from orion.core.approvals import ApprovalGate
from orion.core.engine import ExecutionEngine, PlannedStep, default_registry
from orion.core.models import Task, ToolSafetyLevel
from orion.core.registry import ToolDefinition
from orion.db.session import init_db
from orion.db.task_store import PersistentTaskStore
from orion.db.event_store import PersistentEventStore

# Ensure database tables exist before creating the stores
init_db()

store = PersistentTaskStore()
events = PersistentEventStore()
registry = default_registry()
approval_gate = ApprovalGate(store)

# Import planner lazily to avoid circular imports at module level
from orion.core.planner import LLMPlanner  # noqa: E402
from orion.config import config as _cfg  # noqa: E402

planner = LLMPlanner(registry=registry, llm_provider=_cfg.llm_provider)
engine = ExecutionEngine(
    store=store,
    events=events,
    registry=registry,
    approval_gate=approval_gate,
    planner=planner,
)


# ── OpenClaw-backed tools ─────────────────────────────────────────────────────
#
# Every tool that changes something outside Orion is declared here, once, with
# its safety level. The MCP layer calls ``run_gated_tool`` and never talks to
# OpenClaw directly for these, so the approval gate cannot be skipped.

def _register_openclaw_tool(
    name: str,
    description: str,
    input_model: type[BaseModel],
    safety_level: ToolSafetyLevel,
    render: Callable[[Any], str],
) -> None:
    """Register a tool whose handler sends ``render(payload)`` to OpenClaw."""

    async def handler(payload: Any) -> dict[str, str]:
        result = await get_openclaw_client().send_task(render(payload))
        if result["status"] != "success":
            raise RuntimeError(result["result"])
        return {"message": result["result"]}

    registry.register(
        ToolDefinition(
            name=name,
            description=description,
            input_model=input_model,
            handler=handler,
            safety_level=safety_level,
        )
    )


class OpenClawSendEmailInput(BaseModel):
    to: str
    subject: str
    body: str


class OpenClawSendMessageInput(BaseModel):
    recipient: str
    message: str


class OpenClawSendSlackInput(BaseModel):
    channel: str
    message: str


class OpenClawWriteFileInput(BaseModel):
    path: str
    content: str


class OpenClawRunCommandInput(BaseModel):
    command: str


class OpenClawRunCodeInput(BaseModel):
    code: str
    language: str = "python"


class OpenClawCreateEventInput(BaseModel):
    title: str
    date: str
    time: str
    duration: str = "1 hour"
    attendees: str = ""


class OpenClawRescheduleEventInput(BaseModel):
    event_name: str
    new_date: str = ""
    new_time: str = ""


def _render_create_event(p: OpenClawCreateEventInput) -> str:
    task = f"Create a calendar event titled '{p.title}' on {p.date} at {p.time}, lasting {p.duration}."
    if p.attendees:
        task += f" Invite: {p.attendees}."
    return task


def _render_reschedule_event(p: OpenClawRescheduleEventInput) -> str:
    task = f"Reschedule my '{p.event_name}' event"
    if p.new_date:
        task += f" to {p.new_date}"
    if p.new_time:
        task += f" at {p.new_time}"
    return task + "."


_EXTERNAL = ToolSafetyLevel.EXTERNAL_SIDE_EFFECT
_DESTRUCTIVE = ToolSafetyLevel.DESTRUCTIVE

_register_openclaw_tool(
    "openclaw_send_email",
    "Send an email via OpenClaw (approval-gated)",
    OpenClawSendEmailInput,
    _EXTERNAL,
    lambda p: f"Send an email to {p.to} with subject '{p.subject}' and body: {p.body}",
)
_register_openclaw_tool(
    "openclaw_send_whatsapp",
    "Send a WhatsApp message via OpenClaw (approval-gated)",
    OpenClawSendMessageInput,
    _EXTERNAL,
    lambda p: f"Send a WhatsApp message to {p.recipient}: {p.message}",
)
_register_openclaw_tool(
    "openclaw_send_telegram",
    "Send a Telegram message via OpenClaw (approval-gated)",
    OpenClawSendMessageInput,
    _EXTERNAL,
    lambda p: f"Send a Telegram message to {p.recipient}: {p.message}",
)
_register_openclaw_tool(
    "openclaw_send_slack",
    "Send a Slack message via OpenClaw (approval-gated)",
    OpenClawSendSlackInput,
    _EXTERNAL,
    lambda p: f"Send a Slack message to {p.channel}: {p.message}",
)
_register_openclaw_tool(
    "openclaw_create_event",
    "Create a calendar event, inviting attendees if given (approval-gated)",
    OpenClawCreateEventInput,
    _EXTERNAL,
    _render_create_event,
)
_register_openclaw_tool(
    "openclaw_reschedule_event",
    "Move an existing calendar event, notifying its attendees (approval-gated)",
    OpenClawRescheduleEventInput,
    _EXTERNAL,
    _render_reschedule_event,
)
_register_openclaw_tool(
    "openclaw_write_file",
    "Write content to a file via OpenClaw (approval-gated)",
    OpenClawWriteFileInput,
    _DESTRUCTIVE,
    lambda p: f"Write the following content to the file at '{p.path}':\n{p.content}",
)
_register_openclaw_tool(
    "openclaw_run_command",
    "Execute a shell command via OpenClaw (approval-gated)",
    OpenClawRunCommandInput,
    _DESTRUCTIVE,
    lambda p: f"Run the following shell command and tell me the output: {p.command}",
)
_register_openclaw_tool(
    "openclaw_run_code",
    "Execute a code snippet via OpenClaw (approval-gated)",
    OpenClawRunCodeInput,
    _DESTRUCTIVE,
    lambda p: f"Run the following {p.language} code and tell me the output:\n{p.code}",
)


async def run_gated_tool(tool_name: str, user_intent: str, **tool_args: Any) -> Task:
    """Run a single registered tool as a task, under the approval gate.

    This is the path voice tools use: the voice LLM has already chosen the
    tool, so the planner is skipped, but the engine still enforces approval.
    """
    tool = registry.get(tool_name)
    return await engine.create_task_with_steps(
        user_intent=user_intent,
        steps=[
            PlannedStep(
                name=tool_name.removeprefix("openclaw_"),
                description=tool.description,
                tool_name=tool_name,
                tool_args=tool_args,
            )
        ],
    )


# ── Memory tools — READ_ONLY / LOW_RISK ──────────────────────────────────────

class MemoryRememberInput(BaseModel):
    key: str
    value: str


class MemoryRecallInput(BaseModel):
    topic: str


class MemoryForgetInput(BaseModel):
    key: str


def _memory_remember_handler(payload: MemoryRememberInput) -> dict[str, str]:
    from orion.services.memory import memory_service
    memory_service.remember(key=payload.key, value=payload.value)
    return {"message": f"Remembered: {payload.key} = {payload.value}"}


def _memory_recall_handler(payload: MemoryRecallInput) -> dict[str, str]:
    from orion.services.memory import memory_service
    results = memory_service.recall(payload.topic)
    if not results:
        return {"message": f"Nothing stored about '{payload.topic}'"}
    lines = [f"{m.key}: {m.value}" for m in results]
    return {"message": "\n".join(lines)}


def _memory_forget_handler(payload: MemoryForgetInput) -> dict[str, str]:
    from orion.services.memory import memory_service
    found = memory_service.forget(payload.key)
    if found:
        return {"message": f"Forgot '{payload.key}'"}
    return {"message": f"Nothing to forget about '{payload.key}'"}


registry.register(
    ToolDefinition(
        name="memory_remember",
        description="Store a fact in long-term memory (key/value)",
        input_model=MemoryRememberInput,
        handler=_memory_remember_handler,
        safety_level=ToolSafetyLevel.LOW_RISK,
    )
)

registry.register(
    ToolDefinition(
        name="memory_recall",
        description="Search long-term memory for facts about a topic",
        input_model=MemoryRecallInput,
        handler=_memory_recall_handler,
        safety_level=ToolSafetyLevel.READ_ONLY,
    )
)

registry.register(
    ToolDefinition(
        name="memory_forget",
        description="Remove a fact from long-term memory",
        input_model=MemoryForgetInput,
        handler=_memory_forget_handler,
        safety_level=ToolSafetyLevel.LOW_RISK,
    )
)
