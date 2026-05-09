from __future__ import annotations

from orion.core.models import ApprovalRequest, TaskStep
from orion.core.store import InMemoryTaskStore


class ApprovalGate:
    """Central gate to enforce human approval before risky tool execution."""

    def __init__(self, store: InMemoryTaskStore) -> None:
        self._store = store

    def create_request(
        self,
        *,
        task_id: str,
        step: TaskStep,
        tool_name: str,
        reason: str,
    ) -> ApprovalRequest:
        request = ApprovalRequest(
            task_id=task_id,
            step_id=step.id,
            tool_name=tool_name,
            reason=reason,
        )
        return self._store.create_approval_request(request)

    def grant_latest_for_task(self, task_id: str, approved_by: str) -> ApprovalRequest:
        request = self._store.get_latest_pending_approval(task_id)
        if not request:
            raise ValueError(f"No pending approval exists for task {task_id}")
        return self._store.grant_approval(request.id, approved_by)
