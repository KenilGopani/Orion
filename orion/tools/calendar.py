"""
Calendar tools — check events, create meetings, reschedule via OpenClaw.
"""

from __future__ import annotations
from bridge import get_openclaw_client
from orion.tools._gated import run_gated


def register(mcp):

    @mcp.tool()
    async def get_events(date: str = "today", count: int = 5) -> str:
        """
        Check the user's calendar for upcoming events.

        Args:
            date: Date to check — "today", "tomorrow", or a specific date like "2025-01-15".
            count: Maximum number of events to return.
        """
        task = f"Check my calendar for {date}. Show me the next {count} events."
        result = await get_openclaw_client().send_task(task)
        return result["result"]

    @mcp.tool()
    async def create_event(
        title: str,
        date: str,
        time: str,
        duration: str = "1 hour",
        attendees: str = "",
    ) -> str:
        """
        Create a new calendar event.
        Requires approval before execution, since attendees receive invites.

        Args:
            title: Event title / subject.
            date: Date of the event (e.g. "2025-01-15" or "next Monday").
            time: Start time (e.g. "10:00 AM" or "14:30").
            duration: How long the event lasts (e.g. "1 hour", "30 minutes").
            attendees: Comma-separated list of attendee names or emails (optional).
        """
        return await run_gated(
            "openclaw_create_event",
            f"Create event: {title} on {date} at {time}",
            f"The '{title}' event",
            title=title,
            date=date,
            time=time,
            duration=duration,
            attendees=attendees,
        )

    @mcp.tool()
    async def reschedule_event(
        event_name: str,
        new_date: str = "",
        new_time: str = "",
    ) -> str:
        """
        Reschedule an existing calendar event.
        Requires approval before execution, since attendees are notified.

        Args:
            event_name: Name or description of the event to reschedule.
            new_date: New date for the event (optional if only changing time).
            new_time: New time for the event (optional if only changing date).
        """
        return await run_gated(
            "openclaw_reschedule_event",
            f"Reschedule event: {event_name}",
            f"Rescheduling '{event_name}'",
            event_name=event_name,
            new_date=new_date,
            new_time=new_time,
        )
