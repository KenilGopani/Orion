from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class ToolSafetyLevel(str, Enum):
    READ_ONLY = "READ_ONLY"
    LOW_RISK = "LOW_RISK"
    EXTERNAL_SIDE_EFFECT = "EXTERNAL_SIDE_EFFECT"
    DESTRUCTIVE = "DESTRUCTIVE"


class ToolCall(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    safety_level: ToolSafetyLevel
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None


class ToolResult(BaseModel):
    success: bool
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class TaskStep(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    description: str
    status: StepStatus = StepStatus.PENDING
    planned_tool_name: str | None = None
    planned_tool_args: dict[str, Any] = Field(default_factory=dict)
    tool_call: ToolCall | None = None
    tool_result: ToolResult | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ApprovalRequest(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    task_id: str
    step_id: str
    tool_name: str
    reason: str
    created_at: datetime = Field(default_factory=utc_now)
    approved_at: datetime | None = None
    rejected_at: datetime | None = None
    approved_by: str | None = None


class Task(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    user_intent: str
    status: TaskStatus = TaskStatus.PENDING
    steps: list[TaskStep] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    error: str | None = None


class RuntimeEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    task_id: str
    event_type: str
    timestamp: datetime = Field(default_factory=utc_now)
    payload: dict[str, Any] = Field(default_factory=dict)
