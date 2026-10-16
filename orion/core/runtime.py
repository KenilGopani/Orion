"""
Runtime wiring — builds the one set of services an Orion process uses.

Nothing here runs at import time. ``build_runtime()`` is called once by the
app (or by a dev tool / test) and the resulting ``Runtime`` is passed to
whatever needs it, so every part of a process shares one engine.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, NamedTuple

from pydantic import BaseModel

from bridge import get_openclaw_client
from orion.config import Config, config as default_config
from orion.core.approvals import ApprovalGate
from orion.core.engine import ExecutionEngine, PlannedStep, default_registry
from orion.core.models import Task, ToolSafetyLevel
from orion.core.planner import LLMPlanner
from orion.core.registry import ToolDefinition, ToolRegistry
from orion.db.event_store import PersistentEventStore
from orion.db.task_store import PersistentTaskStore

if TYPE_CHECKING:
    from orion.services.scheduler import OrionScheduler


# ── OpenClaw-backed tools ─────────────────────────────────────────────────────
#
# Every tool that changes something outside Orion is declared here, once, with
# its safety level. The MCP layer calls ``Runtime.run_tool`` and never talks to
# OpenClaw directly for these, so the approval gate cannot be skipped.

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


class _OpenClawTool(NamedTuple):
    name: str
    description: str
    input_model: type[BaseModel]
    safety_level: ToolSafetyLevel
    render: Callable[[Any], str]


_EXTERNAL = ToolSafetyLevel.EXTERNAL_SIDE_EFFECT
_DESTRUCTIVE = ToolSafetyLevel.DESTRUCTIVE

OPENCLAW_TOOLS: tuple[_OpenClawTool, ...] = (
    _OpenClawTool(
        "openclaw_send_email",
        "Send an email via OpenClaw (approval-gated)",
        OpenClawSendEmailInput,
        _EXTERNAL,
        lambda p: f"Send an email to {p.to} with subject '{p.subject}' and body: {p.body}",
    ),
    _OpenClawTool(
        "openclaw_send_whatsapp",
        "Send a WhatsApp message via OpenClaw (approval-gated)",
        OpenClawSendMessageInput,
        _EXTERNAL,
        lambda p: f"Send a WhatsApp message to {p.recipient}: {p.message}",
    ),
    _OpenClawTool(
        "openclaw_send_telegram",
        "Send a Telegram message via OpenClaw (approval-gated)",
        OpenClawSendMessageInput,
        _EXTERNAL,
        lambda p: f"Send a Telegram message to {p.recipient}: {p.message}",
    ),
    _OpenClawTool(
        "openclaw_send_slack",
        "Send a Slack message via OpenClaw (approval-gated)",
        OpenClawSendSlackInput,
        _EXTERNAL,
        lambda p: f"Send a Slack message to {p.channel}: {p.message}",
    ),
    _OpenClawTool(
        "openclaw_create_event",
        "Create a calendar event, inviting attendees if given (approval-gated)",
        OpenClawCreateEventInput,
        _EXTERNAL,
        _render_create_event,
    ),
    _OpenClawTool(
        "openclaw_reschedule_event",
        "Move an existing calendar event, notifying its attendees (approval-gated)",
        OpenClawRescheduleEventInput,
        _EXTERNAL,
        _render_reschedule_event,
    ),
    _OpenClawTool(
        "openclaw_write_file",
        "Write content to a file via OpenClaw (approval-gated)",
        OpenClawWriteFileInput,
        _DESTRUCTIVE,
        lambda p: f"Write the following content to the file at '{p.path}':\n{p.content}",
    ),
    _OpenClawTool(
        "openclaw_run_command",
        "Execute a shell command via OpenClaw (approval-gated)",
        OpenClawRunCommandInput,
        _DESTRUCTIVE,
        lambda p: f"Run the following shell command and tell me the output: {p.command}",
    ),
    _OpenClawTool(
        "openclaw_run_code",
        "Execute a code snippet via OpenClaw (approval-gated)",
        OpenClawRunCodeInput,
        _DESTRUCTIVE,
        lambda p: f"Run the following {p.language} code and tell me the output:\n{p.code}",
    ),
)


def _openclaw_handler(render: Callable[[Any], str]) -> Callable[[Any], Any]:
    """Build a handler that sends ``render(payload)`` to OpenClaw."""

    async def handler(payload: Any) -> dict[str, str]:
        result = await get_openclaw_client().send_task(render(payload))
        if result["status"] != "success":
            raise RuntimeError(result["result"])
        return {"message": result["result"]}

    return handler


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


# ── Assembly ──────────────────────────────────────────────────────────────────

def build_registry() -> ToolRegistry:
    """Return a registry holding every tool the engine can execute."""
    registry = default_registry()

    for tool in OPENCLAW_TOOLS:
        registry.register(
            ToolDefinition(
                name=tool.name,
                description=tool.description,
                input_model=tool.input_model,
                handler=_openclaw_handler(tool.render),
                safety_level=tool.safety_level,
            )
        )

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
    return registry


@dataclass
class Runtime:
    """The services one Orion process shares. Build it with ``build_runtime``."""

    config: Config
    store: PersistentTaskStore
    events: PersistentEventStore
    registry: ToolRegistry
    approval_gate: ApprovalGate
    planner: LLMPlanner
    engine: ExecutionEngine
    #: Set by the app while it is serving and the scheduler is enabled.
    scheduler: OrionScheduler | None = None

    async def run_tool(self, tool_name: str, user_intent: str, **tool_args: Any) -> Task:
        """Run a single registered tool as a task, under the approval gate.

        This is the path voice tools use: the voice LLM has already chosen the
        tool, so the planner is skipped, but the engine still enforces approval.
        """
        tool = self.registry.get(tool_name)
        return await self.engine.create_task_with_steps(
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


def build_runtime(cfg: Config | None = None) -> Runtime:
    """Construct the services for one process.

    Opens no database connection; call ``orion.db.session.init_db()`` before
    the first task is created.
    """
    cfg = cfg or default_config
    store = PersistentTaskStore()
    events = PersistentEventStore()
    registry = build_registry()
    approval_gate = ApprovalGate(store)
    planner = LLMPlanner(registry=registry, llm_provider=cfg.llm_provider)
    engine = ExecutionEngine(
        store=store,
        events=events,
        registry=registry,
        approval_gate=approval_gate,
        planner=planner,
    )
    return Runtime(
        config=cfg,
        store=store,
        events=events,
        registry=registry,
        approval_gate=approval_gate,
        planner=planner,
        engine=engine,
    )
