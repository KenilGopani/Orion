"""
Calendar tools — check, create and reschedule events via OpenClaw.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from orion.core.models import ToolSafetyLevel
from orion.core.registry import ToolDefinition
from orion.tools._openclaw import openclaw_tool


class GetEventsInput(BaseModel):
    date: str = Field("today", description='"today", "tomorrow", or a date like "2025-01-15".')
    count: int = Field(5, description="Maximum number of events to return.")


class CreateEventInput(BaseModel):
    title: str = Field(description="Event title / subject.")
    date: str = Field(description='Date of the event, e.g. "2025-01-15" or "next Monday".')
    time: str = Field(description='Start time, e.g. "10:00 AM" or "14:30".')
    duration: str = Field("1 hour", description='How long it lasts, e.g. "30 minutes".')
    attendees: str = Field("", description="Comma-separated attendee names or emails (optional).")


class RescheduleEventInput(BaseModel):
    event_name: str = Field(description="Name or description of the event to reschedule.")
    new_date: str = Field("", description="New date (optional if only changing the time).")
    new_time: str = Field("", description="New time (optional if only changing the date).")


def _render_create_event(p: CreateEventInput) -> str:
    task = f"Create a calendar event titled '{p.title}' on {p.date} at {p.time}, lasting {p.duration}."
    if p.attendees:
        task += f" Invite: {p.attendees}."
    return task


def _render_reschedule_event(p: RescheduleEventInput) -> str:
    task = f"Reschedule my '{p.event_name}' event"
    if p.new_date:
        task += f" to {p.new_date}"
    if p.new_time:
        task += f" at {p.new_time}"
    return task + "."


TOOLS: list[ToolDefinition[Any]] = [
    openclaw_tool(
        name="get_events",
        description="Check the user's calendar for upcoming events.",
        input_model=GetEventsInput,
        safety_level=ToolSafetyLevel.READ_ONLY,
        render=lambda p: f"Check my calendar for {p.date}. Show me the next {p.count} events.",
        action="Checking your calendar",
    ),
    openclaw_tool(
        name="create_event",
        description=(
            "Create a new calendar event. "
            "Requires approval before execution, since attendees receive invites."
        ),
        input_model=CreateEventInput,
        safety_level=ToolSafetyLevel.EXTERNAL_SIDE_EFFECT,
        render=_render_create_event,
        action="The event",
        describe=lambda p: f"Create event: {p.title} on {p.date} at {p.time}",
    ),
    openclaw_tool(
        name="reschedule_event",
        description=(
            "Reschedule an existing calendar event. "
            "Requires approval before execution, since attendees are notified."
        ),
        input_model=RescheduleEventInput,
        safety_level=ToolSafetyLevel.EXTERNAL_SIDE_EFFECT,
        render=_render_reschedule_event,
        action="Rescheduling the event",
        describe=lambda p: f"Reschedule event: {p.event_name}",
    ),
]
