from __future__ import annotations

from typing import Protocol

from orion.core.models import ApprovalRequest, TaskStep


class ApprovalStore(Protocol):
    """The slice of a task store the approval gate depends on.

    Both ``InMemoryTaskStore`` and ``PersistentTaskStore`` satisfy this, so the
    gate works with either without importing a concrete implementation.
    """

    def create_approval_request(self, request: ApprovalRequest) -> ApprovalRequest: ...

    def get_latest_pending_approval(self, task_id: str) -> ApprovalRequest | None: ...

    def grant_approval(self, approval_id: str, approved_by: str) -> ApprovalRequest: ...

    def reject_approval(self, approval_id: str, rejected_by: str) -> ApprovalRequest: ...


class ApprovalGate:
    """Central gate to enforce human approval before risky tool execution."""

    def __init__(self, store: ApprovalStore) -> None:
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

    def reject_latest_for_task(self, task_id: str, rejected_by: str) -> ApprovalRequest:
        request = self._store.get_latest_pending_approval(task_id)
        if not request:
            raise ValueError(f"No pending approval exists for task {task_id}")
        return self._store.reject_approval(request.id, rejected_by)
