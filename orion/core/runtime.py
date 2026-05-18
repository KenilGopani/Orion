from __future__ import annotations

from pydantic import BaseModel

from bridge import get_openclaw_client
from orion.core.approvals import ApprovalGate
from orion.core.engine import ExecutionEngine, PlannedStep, default_registry
from orion.core.models import Task, ToolSafetyLevel
from orion.core.registry import ToolDefinition
from orion.db.session import init_db
from orion.db.task_store import PersistentTaskStore
from orion.db.event_store import PersistentEventStore


class OpenClawSendEmailInput(BaseModel):
    to: str
    subject: str
    body: str


async def _openclaw_send_email_handler(payload: OpenClawSendEmailInput) -> dict[str, str]:
    task = (
        f"Send an email to {payload.to} "
        f"with subject '{payload.subject}' and body: {payload.body}"
    )
    result = await get_openclaw_client().send_task(task)
    if result["status"] != "success":
        raise RuntimeError(result["result"])
    return {"message": result["result"]}


# Ensure database tables exist before creating the stores
init_db()

store = PersistentTaskStore()
events = PersistentEventStore()
registry = default_registry()
approval_gate = ApprovalGate(store)
engine = ExecutionEngine(
    store=store,
    events=events,
    registry=registry,
    approval_gate=approval_gate,
)

registry.register(
    ToolDefinition(
        name="openclaw_send_email",
        description="Send an email via OpenClaw through Orion runtime",
        input_model=OpenClawSendEmailInput,
        handler=_openclaw_send_email_handler,
        safety_level=ToolSafetyLevel.EXTERNAL_SIDE_EFFECT,
    )
)


async def run_runtime_send_email(to: str, subject: str, body: str) -> Task:
    return await engine.create_task_with_steps(
        user_intent=f"Send email to {to} with subject {subject}",
        steps=[
            PlannedStep(
                name="send_email",
                description="Send email through OpenClaw backend",
                tool_name="openclaw_send_email",
                tool_args={"to": to, "subject": subject, "body": body},
            )
        ],
    )


class OpenClawSendWhatsAppInput(BaseModel):
    recipient: str
    message: str


async def _openclaw_send_whatsapp_handler(payload: OpenClawSendWhatsAppInput) -> dict[str, str]:
    task = f"Send a WhatsApp message to {payload.recipient}: {payload.message}"
    result = await get_openclaw_client().send_task(task)
    if result["status"] != "success":
        raise RuntimeError(result["result"])
    return {"message": result["result"]}


registry.register(
    ToolDefinition(
        name="openclaw_send_whatsapp",
        description="Send a WhatsApp message via OpenClaw through Orion runtime",
        input_model=OpenClawSendWhatsAppInput,
        handler=_openclaw_send_whatsapp_handler,
        safety_level=ToolSafetyLevel.EXTERNAL_SIDE_EFFECT,
    )
)


async def run_runtime_send_whatsapp(recipient: str, message: str) -> Task:
    return await engine.create_task_with_steps(
        user_intent=f"WhatsApp {recipient}: {message[:80]}",
        steps=[
            PlannedStep(
                name="send_whatsapp",
                description="Send WhatsApp message through OpenClaw backend",
                tool_name="openclaw_send_whatsapp",
                tool_args={"recipient": recipient, "message": message},
            )
        ],
    )


# ── write_file — DESTRUCTIVE (can overwrite any file) ────────────────────────

class OpenClawWriteFileInput(BaseModel):
    path: str
    content: str


async def _openclaw_write_file_handler(payload: OpenClawWriteFileInput) -> dict[str, str]:
    task = f"Write the following content to the file at '{payload.path}':\n{payload.content}"
    result = await get_openclaw_client().send_task(task)
    if result["status"] != "success":
        raise RuntimeError(result["result"])
    return {"message": result["result"]}


registry.register(
    ToolDefinition(
        name="openclaw_write_file",
        description="Write content to a file via OpenClaw (approval-gated)",
        input_model=OpenClawWriteFileInput,
        handler=_openclaw_write_file_handler,
        safety_level=ToolSafetyLevel.DESTRUCTIVE,
    )
)


async def run_runtime_write_file(path: str, content: str) -> Task:
    return await engine.create_task_with_steps(
        user_intent=f"Write file: {path}",
        steps=[
            PlannedStep(
                name="write_file",
                description="Write file through OpenClaw backend",
                tool_name="openclaw_write_file",
                tool_args={"path": path, "content": content},
            )
        ],
    )


# ── run_command — DESTRUCTIVE (arbitrary shell execution) ─────────────────────

class OpenClawRunCommandInput(BaseModel):
    command: str


async def _openclaw_run_command_handler(payload: OpenClawRunCommandInput) -> dict[str, str]:
    task = f"Run the following shell command and tell me the output: {payload.command}"
    result = await get_openclaw_client().send_task(task)
    if result["status"] != "success":
        raise RuntimeError(result["result"])
    return {"message": result["result"]}


registry.register(
    ToolDefinition(
        name="openclaw_run_command",
        description="Execute a shell command via OpenClaw (approval-gated)",
        input_model=OpenClawRunCommandInput,
        handler=_openclaw_run_command_handler,
        safety_level=ToolSafetyLevel.DESTRUCTIVE,
    )
)


async def run_runtime_run_command(command: str) -> Task:
    return await engine.create_task_with_steps(
        user_intent=f"Run command: {command[:80]}",
        steps=[
            PlannedStep(
                name="run_command",
                description="Execute shell command through OpenClaw backend",
                tool_name="openclaw_run_command",
                tool_args={"command": command},
            )
        ],
    )


# ── send_telegram — EXTERNAL_SIDE_EFFECT ─────────────────────────────────────

class OpenClawSendTelegramInput(BaseModel):
    recipient: str
    message: str


async def _openclaw_send_telegram_handler(payload: OpenClawSendTelegramInput) -> dict[str, str]:
    task = f"Send a Telegram message to {payload.recipient}: {payload.message}"
    result = await get_openclaw_client().send_task(task)
    if result["status"] != "success":
        raise RuntimeError(result["result"])
    return {"message": result["result"]}


registry.register(
    ToolDefinition(
        name="openclaw_send_telegram",
        description="Send a Telegram message via OpenClaw (approval-gated)",
        input_model=OpenClawSendTelegramInput,
        handler=_openclaw_send_telegram_handler,
        safety_level=ToolSafetyLevel.EXTERNAL_SIDE_EFFECT,
    )
)


async def run_runtime_send_telegram(recipient: str, message: str) -> Task:
    return await engine.create_task_with_steps(
        user_intent=f"Telegram {recipient}: {message[:80]}",
        steps=[
            PlannedStep(
                name="send_telegram",
                description="Send Telegram message through OpenClaw backend",
                tool_name="openclaw_send_telegram",
                tool_args={"recipient": recipient, "message": message},
            )
        ],
    )


# ── send_slack — EXTERNAL_SIDE_EFFECT ────────────────────────────────────────

class OpenClawSendSlackInput(BaseModel):
    channel: str
    message: str


async def _openclaw_send_slack_handler(payload: OpenClawSendSlackInput) -> dict[str, str]:
    task = f"Send a Slack message to {payload.channel}: {payload.message}"
    result = await get_openclaw_client().send_task(task)
    if result["status"] != "success":
        raise RuntimeError(result["result"])
    return {"message": result["result"]}


registry.register(
    ToolDefinition(
        name="openclaw_send_slack",
        description="Send a Slack message via OpenClaw (approval-gated)",
        input_model=OpenClawSendSlackInput,
        handler=_openclaw_send_slack_handler,
        safety_level=ToolSafetyLevel.EXTERNAL_SIDE_EFFECT,
    )
)


async def run_runtime_send_slack(channel: str, message: str) -> Task:
    return await engine.create_task_with_steps(
        user_intent=f"Slack {channel}: {message[:80]}",
        steps=[
            PlannedStep(
                name="send_slack",
                description="Send Slack message through OpenClaw backend",
                tool_name="openclaw_send_slack",
                tool_args={"channel": channel, "message": message},
            )
        ],
    )
