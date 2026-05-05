from __future__ import annotations

from collections import defaultdict
from threading import RLock

from orion.core.models import ApprovalRequest, Task, TaskStatus, TaskStep, utc_now


class InMemoryTaskStore:
    """Simple in-memory persistence for tasks, steps, and approvals."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._tasks: dict[str, Task] = {}
        self._approvals_by_task: dict[str, list[ApprovalRequest]] = defaultdict(list)
        self._approvals_by_id: dict[str, ApprovalRequest] = {}

    def create_task(self, user_intent: str) -> Task:
        with self._lock:
            task = Task(user_intent=user_intent)
            self._tasks[task.id] = task
            return task

    def get_task(self, task_id: str) -> Task | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self) -> list[Task]:
        with self._lock:
            return list(self._tasks.values())

    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        *,
        error: str | None = None,
    ) -> Task:
        with self._lock:
            task = self._must_get_task(task_id)
            task.status = status
            task.error = error
            task.updated_at = utc_now()
            return task

    def append_step(self, task_id: str, step: TaskStep) -> TaskStep:
        with self._lock:
            task = self._must_get_task(task_id)
            task.steps.append(step)
            task.updated_at = utc_now()
            return step

    def update_step(self, task_id: str, step: TaskStep) -> TaskStep:
        with self._lock:
            task = self._must_get_task(task_id)
            for index, existing in enumerate(task.steps):
                if existing.id == step.id:
                    step.updated_at = utc_now()
                    task.steps[index] = step
                    task.updated_at = utc_now()
                    return step
            raise KeyError(f"Step {step.id} not found for task {task_id}")

    def create_approval_request(self, approval: ApprovalRequest) -> ApprovalRequest:
        with self._lock:
            self._must_get_task(approval.task_id)
            self._approvals_by_task[approval.task_id].append(approval)
            self._approvals_by_id[approval.id] = approval
            return approval

    def list_approval_requests(self, task_id: str) -> list[ApprovalRequest]:
        with self._lock:
            return list(self._approvals_by_task.get(task_id, []))

    def get_latest_pending_approval(self, task_id: str) -> ApprovalRequest | None:
        with self._lock:
            approvals = self._approvals_by_task.get(task_id, [])
            for approval in reversed(approvals):
                if approval.approved_at is None and approval.rejected_at is None:
                    return approval
            return None

    def grant_approval(self, approval_id: str, approved_by: str) -> ApprovalRequest:
        with self._lock:
            approval = self._approvals_by_id.get(approval_id)
            if not approval:
                raise KeyError(f"Approval {approval_id} not found")
            approval.approved_by = approved_by
            approval.approved_at = utc_now()
            return approval

    def _must_get_task(self, task_id: str) -> Task:
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")
        return task
