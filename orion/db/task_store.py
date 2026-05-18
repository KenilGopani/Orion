"""
Persistent task store backed by SQLite via SQLModel.

Implements the same interface as ``InMemoryTaskStore`` so it can be
used as a drop-in replacement.
"""

from __future__ import annotations

import json
from typing import Any

from sqlmodel import select

from orion.core.models import (
    ApprovalRequest,
    StepStatus,
    Task,
    TaskStatus,
    TaskStep,
    ToolCall,
    ToolResult,
    utc_now,
)
from orion.db.models import ApprovalRecord, TaskRecord, TaskStepRecord
from orion.db.session import get_session


# ── Serialisation helpers ─────────────────────────────────────────────────────

def _step_to_record(task_id: str, step: TaskStep) -> TaskStepRecord:
    """Convert a Pydantic TaskStep to a SQLModel record."""
    return TaskStepRecord(
        id=step.id,
        task_id=task_id,
        name=step.name,
        description=step.description,
        status=step.status.value if isinstance(step.status, StepStatus) else step.status,
        planned_tool_name=step.planned_tool_name or "",
        planned_tool_args=json.dumps(step.planned_tool_args),
        tool_call_json=step.tool_call.model_dump_json() if step.tool_call else None,
        tool_result_output=json.dumps(step.tool_result.output) if step.tool_result else None,
        tool_result_success=step.tool_result.success if step.tool_result else None,
        error=step.error,
        created_at=step.created_at,
        updated_at=step.updated_at,
    )


def _record_to_step(rec: TaskStepRecord) -> TaskStep:
    """Convert a SQLModel record back to a Pydantic TaskStep."""
    tool_call = None
    if rec.tool_call_json:
        tool_call = ToolCall.model_validate_json(rec.tool_call_json)

    tool_result = None
    if rec.tool_result_success is not None:
        tool_result = ToolResult(
            success=rec.tool_result_success,
            output=json.loads(rec.tool_result_output) if rec.tool_result_output else {},
        )

    return TaskStep(
        id=rec.id,
        name=rec.name,
        description=rec.description,
        status=StepStatus(rec.status),
        planned_tool_name=rec.planned_tool_name or None,
        planned_tool_args=json.loads(rec.planned_tool_args) if rec.planned_tool_args else {},
        tool_call=tool_call,
        tool_result=tool_result,
        error=rec.error,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
    )


def _record_to_task(task_rec: TaskRecord, step_recs: list[TaskStepRecord]) -> Task:
    """Reconstruct a full Task from its record and associated step records."""
    return Task(
        id=task_rec.id,
        user_intent=task_rec.user_intent,
        status=TaskStatus(task_rec.status),
        steps=[_record_to_step(s) for s in step_recs],
        created_at=task_rec.created_at,
        updated_at=task_rec.updated_at,
        error=task_rec.error,
    )


def _record_to_approval(rec: ApprovalRecord) -> ApprovalRequest:
    """Convert an ApprovalRecord to the Pydantic model."""
    return ApprovalRequest(
        id=rec.id,
        task_id=rec.task_id,
        step_id=rec.step_id,
        tool_name=rec.tool_name,
        reason=rec.reason,
        created_at=rec.created_at,
        approved_at=rec.approved_at,
        rejected_at=rec.rejected_at,
        approved_by=rec.approved_by,
    )


# ── Store ─────────────────────────────────────────────────────────────────────

class PersistentTaskStore:
    """SQLite-backed task store with the same interface as InMemoryTaskStore."""

    # ── Tasks ─────────────────────────────────────────────────────

    def create_task(self, user_intent: str) -> Task:
        task = Task(user_intent=user_intent)
        rec = TaskRecord(
            id=task.id,
            user_intent=task.user_intent,
            status=task.status.value,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )
        with get_session() as session:
            session.add(rec)
            session.commit()
        return task

    def get_task(self, task_id: str) -> Task | None:
        with get_session() as session:
            task_rec = session.get(TaskRecord, task_id)
            if not task_rec:
                return None
            step_recs = list(
                session.exec(
                    select(TaskStepRecord)
                    .where(TaskStepRecord.task_id == task_id)
                    .order_by(TaskStepRecord.created_at)
                )
            )
            return _record_to_task(task_rec, step_recs)

    def list_tasks(self) -> list[Task]:
        with get_session() as session:
            task_recs = list(session.exec(select(TaskRecord).order_by(TaskRecord.created_at)))
            tasks: list[Task] = []
            for task_rec in task_recs:
                step_recs = list(
                    session.exec(
                        select(TaskStepRecord)
                        .where(TaskStepRecord.task_id == task_rec.id)
                        .order_by(TaskStepRecord.created_at)
                    )
                )
                tasks.append(_record_to_task(task_rec, step_recs))
            return tasks

    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        *,
        error: str | None = None,
    ) -> Task:
        with get_session() as session:
            task_rec = session.get(TaskRecord, task_id)
            if not task_rec:
                raise KeyError(f"Task {task_id} not found")
            task_rec.status = status.value if isinstance(status, TaskStatus) else status
            task_rec.error = error
            task_rec.updated_at = utc_now()
            session.add(task_rec)
            session.commit()
        return self._must_get_task(task_id)

    # ── Steps ─────────────────────────────────────────────────────

    def append_step(self, task_id: str, step: TaskStep) -> TaskStep:
        self._must_get_task(task_id)  # verify exists
        rec = _step_to_record(task_id, step)
        with get_session() as session:
            session.add(rec)
            # Also update parent task timestamp
            task_rec = session.get(TaskRecord, task_id)
            if task_rec:
                task_rec.updated_at = utc_now()
                session.add(task_rec)
            session.commit()
        return step

    def update_step(self, task_id: str, step: TaskStep) -> TaskStep:
        with get_session() as session:
            rec = session.get(TaskStepRecord, step.id)
            if not rec or rec.task_id != task_id:
                raise KeyError(f"Step {step.id} not found for task {task_id}")

            step.updated_at = utc_now()
            rec.name = step.name
            rec.description = step.description
            rec.status = step.status.value if isinstance(step.status, StepStatus) else step.status
            rec.planned_tool_name = step.planned_tool_name or ""
            rec.planned_tool_args = json.dumps(step.planned_tool_args)
            rec.tool_call_json = step.tool_call.model_dump_json() if step.tool_call else None
            rec.tool_result_output = json.dumps(step.tool_result.output) if step.tool_result else None
            rec.tool_result_success = step.tool_result.success if step.tool_result else None
            rec.error = step.error
            rec.updated_at = step.updated_at

            session.add(rec)

            # Update parent task timestamp
            task_rec = session.get(TaskRecord, task_id)
            if task_rec:
                task_rec.updated_at = utc_now()
                session.add(task_rec)
            session.commit()
        return step

    # ── Approvals ─────────────────────────────────────────────────

    def create_approval_request(self, approval: ApprovalRequest) -> ApprovalRequest:
        self._must_get_task(approval.task_id)
        rec = ApprovalRecord(
            id=approval.id,
            task_id=approval.task_id,
            step_id=approval.step_id,
            tool_name=approval.tool_name,
            reason=approval.reason,
            created_at=approval.created_at,
            approved_at=approval.approved_at,
            rejected_at=approval.rejected_at,
            approved_by=approval.approved_by,
        )
        with get_session() as session:
            session.add(rec)
            session.commit()
        return approval

    def list_approval_requests(self, task_id: str) -> list[ApprovalRequest]:
        with get_session() as session:
            recs = list(
                session.exec(
                    select(ApprovalRecord)
                    .where(ApprovalRecord.task_id == task_id)
                    .order_by(ApprovalRecord.created_at)
                )
            )
            return [_record_to_approval(r) for r in recs]

    def get_latest_pending_approval(self, task_id: str) -> ApprovalRequest | None:
        with get_session() as session:
            recs = list(
                session.exec(
                    select(ApprovalRecord)
                    .where(ApprovalRecord.task_id == task_id)
                    .order_by(ApprovalRecord.created_at.desc())  # type: ignore[union-attr]
                )
            )
            for rec in recs:
                if rec.approved_at is None and rec.rejected_at is None:
                    return _record_to_approval(rec)
            return None

    def grant_approval(self, approval_id: str, approved_by: str) -> ApprovalRequest:
        with get_session() as session:
            rec = session.get(ApprovalRecord, approval_id)
            if not rec:
                raise KeyError(f"Approval {approval_id} not found")
            rec.approved_by = approved_by
            rec.approved_at = utc_now()
            session.add(rec)
            session.commit()
            return _record_to_approval(rec)

    # ── Internal ──────────────────────────────────────────────────

    def _must_get_task(self, task_id: str) -> Task:
        task = self.get_task(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")
        return task
