"""
Calendar tools — check events, create meetings, reschedule via OpenClaw.
"""

from __future__ import annotations
from bridge import openclaw_client


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
        result = await openclaw_client.send_task(task)
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

        Args:
            title: Event title / subject.
            date: Date of the event (e.g. "2025-01-15" or "next Monday").
            time: Start time (e.g. "10:00 AM" or "14:30").
            duration: How long the event lasts (e.g. "1 hour", "30 minutes").
            attendees: Comma-separated list of attendee names or emails (optional).
        """
        task = f"Create a calendar event titled '{title}' on {date} at {time}, lasting {duration}."
        if attendees:
            task += f" Invite: {attendees}."
        result = await openclaw_client.send_task(task)
        return result["result"]

    @mcp.tool()
    async def reschedule_event(
        event_name: str,
        new_date: str = "",
        new_time: str = "",
    ) -> str:
        """
        Reschedule an existing calendar event.

        Args:
            event_name: Name or description of the event to reschedule.
            new_date: New date for the event (optional if only changing time).
            new_time: New time for the event (optional if only changing date).
        """
        task = f"Reschedule my '{event_name}' event"
        if new_date:
            task += f" to {new_date}"
        if new_time:
            task += f" at {new_time}"
        task += "."
        result = await openclaw_client.send_task(task)
        return result["result"]
