from __future__ import annotations

from pydantic import BaseModel

from bridge import get_openclaw_client
from orion.core.approvals import ApprovalGate
from orion.core.engine import ExecutionEngine, PlannedStep, default_registry
from orion.core.events import EventRecorder
from orion.core.models import Task, ToolSafetyLevel
from orion.core.registry import ToolDefinition
from orion.core.store import InMemoryTaskStore


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


store = InMemoryTaskStore()
events = EventRecorder()
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
