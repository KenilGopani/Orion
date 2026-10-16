"""
SQLModel table definitions for Orion's persistent storage.

These mirror the Pydantic models in ``orion.core.models`` but are flat,
SQLite-friendly tables with JSON-serialised columns for nested data.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.types import DateTime, TypeDecorator
from sqlmodel import Field, SQLModel


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator[datetime]):
    """Store datetimes as naive UTC; always hand them back timezone-aware.

    SQLite has no timezone support, so without this every timestamp comes back
    naive and serialises without an offset — which browsers then misread as
    local time.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


def _new_id() -> str:
    return str(uuid.uuid4())


class TaskRecord(SQLModel, table=True):
    """Persistent record for a task."""

    __tablename__ = "tasks"

    id: str = Field(default_factory=_new_id, primary_key=True)
    user_intent: str
    status: str = "PENDING"
    error: str | None = None
    created_at: datetime = Field(default_factory=_utc_now, sa_type=UTCDateTime)
    updated_at: datetime = Field(default_factory=_utc_now, sa_type=UTCDateTime)


class TaskStepRecord(SQLModel, table=True):
    """Persistent record for a single step within a task."""

    __tablename__ = "task_steps"

    id: str = Field(default_factory=_new_id, primary_key=True)
    task_id: str = Field(foreign_key="tasks.id", index=True)
    name: str
    description: str = ""
    status: str = "PENDING"
    planned_tool_name: str = ""
    planned_tool_args: str = "{}"  # JSON string
    tool_call_json: str | None = None  # JSON-serialised ToolCall
    tool_result_output: str | None = None  # JSON string
    tool_result_success: bool | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=_utc_now, sa_type=UTCDateTime)
    updated_at: datetime = Field(default_factory=_utc_now, sa_type=UTCDateTime)


class ApprovalRecord(SQLModel, table=True):
    """Persistent record for an approval request."""

    __tablename__ = "approvals"

    id: str = Field(default_factory=_new_id, primary_key=True)
    task_id: str = Field(foreign_key="tasks.id", index=True)
    step_id: str
    tool_name: str
    reason: str
    approved_at: datetime | None = Field(default=None, sa_type=UTCDateTime)
    rejected_at: datetime | None = Field(default=None, sa_type=UTCDateTime)
    approved_by: str | None = None
    created_at: datetime = Field(default_factory=_utc_now, sa_type=UTCDateTime)


class EventRecord(SQLModel, table=True):
    """Persistent record for a runtime event."""

    __tablename__ = "events"

    id: str = Field(default_factory=_new_id, primary_key=True)
    task_id: str = Field(foreign_key="tasks.id", index=True)
    event_type: str
    payload: str = "{}"  # JSON string
    created_at: datetime = Field(default_factory=_utc_now, sa_type=UTCDateTime)


class MemoryRecord(SQLModel, table=True):
    """A single remembered fact — key/value with metadata."""

    __tablename__ = "memories"

    id: str = Field(default_factory=_new_id, primary_key=True)
    key: str = Field(index=True)
    value: str
    source: str = "voice"  # "voice" | "manual" | "system"
    created_at: datetime = Field(default_factory=_utc_now, sa_type=UTCDateTime)
    updated_at: datetime = Field(default_factory=_utc_now, sa_type=UTCDateTime)


class ConversationMessage(SQLModel, table=True):
    """A single message in a conversation session."""

    __tablename__ = "conversation_log"

    id: str = Field(default_factory=_new_id, primary_key=True)
    session_id: str = Field(index=True)
    role: str  # "user" | "assistant"
    content: str
    timestamp: datetime = Field(default_factory=_utc_now, sa_type=UTCDateTime)
