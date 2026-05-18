from __future__ import annotations

import inspect
import logging
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from orion.core.approvals import ApprovalGate
from orion.core.models import (
    StepStatus,
    Task,
    TaskStatus,
    TaskStep,
    ToolCall,
    ToolResult,
    ToolSafetyLevel,
    utc_now,
)
from orion.core.registry import ToolDefinition, ToolRegistry

if TYPE_CHECKING:
    from orion.core.planner import LLMPlanner

logger = logging.getLogger("orion.engine")


class EchoToolInput(BaseModel):
    message: str


class MockSendEmailInput(BaseModel):
    to: str
    subject: str
    body: str


def default_registry() -> ToolRegistry:
    registry = ToolRegistry()

    def echo_handler(payload: EchoToolInput) -> dict[str, Any]:
        return {"echoed": payload.message}

    def mock_send_email_handler(payload: MockSendEmailInput) -> dict[str, Any]:
        return {
            "status": "queued",
            "to": payload.to,
            "subject": payload.subject,
        }

    registry.register(
        ToolDefinition(
            name="echo_tool",
            description="Echoes the message back for testing safe execution",
            input_model=EchoToolInput,
            handler=echo_handler,
            safety_level=ToolSafetyLevel.READ_ONLY,
        )
    )
    registry.register(
        ToolDefinition(
            name="mock_send_email",
            description="Mock email sender used to demonstrate approval flow",
            input_model=MockSendEmailInput,
            handler=mock_send_email_handler,
            safety_level=ToolSafetyLevel.EXTERNAL_SIDE_EFFECT,
        )
    )
    return registry


class PlannedStep(BaseModel):
    name: str
    description: str
    tool_name: str
    tool_args: dict[str, Any] = Field(default_factory=dict)


class ExecutionEngine:
    def __init__(
        self,
        *,
        store: Any,
        events: Any,
        registry: ToolRegistry,
        approval_gate: ApprovalGate,
        planner: LLMPlanner | None = None,
    ) -> None:
        self._store = store
        self._events = events
        self._registry = registry
        self._approval_gate = approval_gate
        self._planner = planner

    async def create_task(self, user_intent: str) -> Task:
        task = self._store.create_task(user_intent=user_intent)
        self._events.record(task.id, "task_created", {"user_intent": user_intent})
        await self._run(task.id)
        updated = self._store.get_task(task.id)
        if not updated:
            raise RuntimeError("Task disappeared after execution")
        return updated

    async def create_task_with_steps(self, user_intent: str, steps: list[PlannedStep]) -> Task:
        task = self._store.create_task(user_intent=user_intent)
        self._events.record(task.id, "task_created", {"user_intent": user_intent})
        self._store.update_task_status(task.id, TaskStatus.PLANNING)
        for planned in steps:
            self._store.append_step(
                task.id,
                TaskStep(
                    name=planned.name,
                    description=planned.description,
                    planned_tool_name=planned.tool_name,
                    planned_tool_args=planned.tool_args,
                ),
            )
        await self._run(task.id)
        return self._must_get_task(task.id)

    async def resume_task_after_approval(self, task_id: str, approved_by: str) -> Task:
        task = self._must_get_task(task_id)
        if task.status != TaskStatus.AWAITING_APPROVAL:
            raise ValueError(f"Task {task_id} is not awaiting approval")

        approval = self._approval_gate.grant_latest_for_task(task_id=task_id, approved_by=approved_by)
        step = self._get_step(task_id, approval.step_id)
        step.status = StepStatus.PENDING
        step.updated_at = utc_now()
        self._store.update_step(task_id, step)
        self._events.record(
            task_id,
            "approval_granted",
            {"approval_id": approval.id, "approved_by": approved_by},
        )
        await self._run(task_id)
        return self._must_get_task(task_id)

    async def _run(self, task_id: str) -> None:
        task = self._must_get_task(task_id)

        if task.status in {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            return

        if not task.steps:
            self._store.update_task_status(task_id, TaskStatus.PLANNING)
            planned_steps = await self._plan(task.user_intent)
            for planned in planned_steps:
                self._store.append_step(
                    task_id,
                    TaskStep(
                        name=planned.name,
                        description=planned.description,
                        planned_tool_name=planned.tool_name,
                        planned_tool_args=planned.tool_args,
                    ),
                )

        self._store.update_task_status(task_id, TaskStatus.RUNNING)
        self._events.record(task_id, "task_started", {"steps": len(self._must_get_task(task_id).steps)})

        for step in self._must_get_task(task_id).steps:
            if step.status == StepStatus.SUCCEEDED:
                continue
            if step.status == StepStatus.AWAITING_APPROVAL:
                self._store.update_task_status(task_id, TaskStatus.AWAITING_APPROVAL)
                return
            await self._execute_step(task_id, step)
            latest_task = self._must_get_task(task_id)
            if latest_task.status in {TaskStatus.AWAITING_APPROVAL, TaskStatus.FAILED}:
                return

        self._store.update_task_status(task_id, TaskStatus.SUCCEEDED)
        self._events.record(task_id, "task_succeeded", {})

    async def _execute_step(self, task_id: str, step: TaskStep) -> None:
        if not step.planned_tool_name:
            raise KeyError(f"Step {step.id} has no planned tool")
        tool = self._registry.get(step.planned_tool_name)

        step.status = StepStatus.RUNNING
        step.updated_at = utc_now()
        self._store.update_step(task_id, step)
        self._events.record(task_id, "step_started", {"step_id": step.id, "step_name": step.name})

        step.tool_call = ToolCall(
            tool_name=tool.name,
            arguments=step.planned_tool_args,
            safety_level=tool.safety_level,
        )

        if tool.requires_approval and not self._can_execute_risky_step(task_id, step.id):
            step.status = StepStatus.AWAITING_APPROVAL
            self._store.update_step(task_id, step)
            approval = self._approval_gate.create_request(
                task_id=task_id,
                step=step,
                tool_name=tool.name,
                reason=f"Tool {tool.name} has safety level {tool.safety_level}",
            )
            self._store.update_task_status(task_id, TaskStatus.AWAITING_APPROVAL)
            self._events.record(
                task_id,
                "approval_required",
                {"approval_id": approval.id, "step_id": step.id, "tool_name": tool.name},
            )
            return

        self._events.record(task_id, "tool_started", {"step_id": step.id, "tool_name": tool.name})

        try:
            validated_input = tool.input_model(**step.planned_tool_args)
            maybe_output = tool.handler(validated_input)
            output = await maybe_output if inspect.isawaitable(maybe_output) else maybe_output
            step.tool_result = ToolResult(success=True, output=output)
            step.status = StepStatus.SUCCEEDED
            step.tool_call.finished_at = utc_now()
            self._store.update_step(task_id, step)
            self._events.record(
                task_id,
                "tool_succeeded",
                {"step_id": step.id, "tool_name": tool.name, "output": output},
            )
        except Exception as exc:
            step.status = StepStatus.FAILED
            step.error = str(exc)
            step.tool_result = ToolResult(success=False, error=str(exc))
            if step.tool_call:
                step.tool_call.finished_at = utc_now()
            self._store.update_step(task_id, step)
            self._store.update_task_status(task_id, TaskStatus.FAILED, error=str(exc))
            self._events.record(
                task_id,
                "tool_failed",
                {"step_id": step.id, "tool_name": tool.name, "error": str(exc)},
            )
            self._events.record(task_id, "task_failed", {"error": str(exc)})

    async def _plan(self, user_intent: str) -> list[PlannedStep]:
        """Decompose user intent into planned steps.

        Delegates to the injected LLMPlanner if available, otherwise
        falls back to the simple keyword-based stub.
        """
        if self._planner:
            plan = await self._planner.plan(user_intent)
            return [
                PlannedStep(
                    name=step.name,
                    description=step.description,
                    tool_name=step.tool_name,
                    tool_args=step.tool_args,
                )
                for step in plan.steps
            ]

        # Fallback: simple keyword-based planning (no LLM)
        intent_lower = user_intent.lower()
        if "email" in intent_lower or "send" in intent_lower:
            return [
                PlannedStep(
                    name="send_mock_email",
                    description="Send a mock email to demonstrate approval-gated action",
                    tool_name="mock_send_email",
                    tool_args={
                        "to": "demo@example.com",
                        "subject": "Orion Demo",
                        "body": user_intent,
                    },
                )
            ]
        return [
            PlannedStep(
                name="echo_intent",
                description="Echo the user intent to prove safe tool flow",
                tool_name="echo_tool",
                tool_args={"message": user_intent},
            )
        ]

    def _can_execute_risky_step(self, task_id: str, step_id: str) -> bool:
        approvals = self._store.list_approval_requests(task_id)
        for approval in reversed(approvals):
            if approval.step_id == step_id and approval.approved_at is not None:
                return True
        return False

    def _must_get_task(self, task_id: str) -> Task:
        task = self._store.get_task(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")
        return task

    def _get_step(self, task_id: str, step_id: str) -> TaskStep:
        task = self._must_get_task(task_id)
        for step in task.steps:
            if step.id == step_id:
                return step
        raise KeyError(f"Step {step_id} not found for task {task_id}")
