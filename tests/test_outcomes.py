"""
Approval outcomes reach the voice session: the event store notifies
subscribers, outcomes are worded for speech, the app streams them, and the
announcer speaks them at a pause.
"""

from __future__ import annotations

import asyncio
import time
import unittest
from dataclasses import replace
from unittest.mock import AsyncMock, patch

import httpx

from tests.conftest import AUTH, live_server, make_app, reset_test_db

from orion.config import config
from orion.core.models import RuntimeEvent
from orion.core.runtime import build_runtime
from orion.services.outcomes import outcome_for
from orion.voice_outcomes import OutcomeAnnouncer


def _openclaw(status: str = "success", result: str = "Message sent to Priya.") -> AsyncMock:
    client = AsyncMock()
    client.send_task.return_value = {"status": status, "result": result}
    return client


class EventSubscriberTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_test_db()
        self.events = build_runtime().events

    def test_subscribers_see_events_until_they_unsubscribe(self) -> None:
        seen: list[str] = []
        unsubscribe = self.events.subscribe(lambda e: seen.append(e.event_type))
        self.events.record("t1", "task_created")
        unsubscribe()
        self.events.record("t1", "task_started")
        self.assertEqual(seen, ["task_created"])

    def test_a_broken_subscriber_never_breaks_recording(self) -> None:
        def broken(event: RuntimeEvent) -> None:
            raise RuntimeError("boom")

        self.events.subscribe(broken)
        self.events.record("t1", "task_created")
        self.assertEqual(len(self.events.list_events("t1")), 1)


class OutcomeWordingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        reset_test_db()
        self.runtime = build_runtime()
        self.seen: list[dict] = []
        self.runtime.events.subscribe(
            lambda e: (o := outcome_for(e, self.runtime)) and self.seen.append(o)
        )

    async def _pending_whatsapp(self) -> str:
        task = await self.runtime.run_tool(
            "send_whatsapp", "WhatsApp Priya", recipient="Priya", message="10 min late"
        )
        return task.id

    async def test_approved_and_sent(self) -> None:
        with patch("orion.tools._openclaw.get_openclaw_client", return_value=_openclaw()):
            task_id = await self._pending_whatsapp()
            self.assertEqual(self.seen, [], "nothing to announce while still pending")
            await self.runtime.engine.resume_task_after_approval(task_id, approved_by="me")
        self.assertEqual(len(self.seen), 1)
        self.assertEqual(self.seen[0]["outcome"], "succeeded")
        self.assertEqual(
            self.seen[0]["speech"],
            "The WhatsApp message you approved went through. Message sent to Priya.",
        )

    async def test_approved_but_failed(self) -> None:
        failing = _openclaw(status="error", result="WhatsApp isn't connected.")
        with patch("orion.tools._openclaw.get_openclaw_client", return_value=failing):
            task_id = await self._pending_whatsapp()
            await self.runtime.engine.resume_task_after_approval(task_id, approved_by="me")
        self.assertEqual(
            self.seen[-1]["speech"],
            "The WhatsApp message you approved didn't go through. WhatsApp isn't connected.",
        )

    async def test_rejected(self) -> None:
        task_id = await self._pending_whatsapp()
        self.runtime.engine.reject_task(task_id, rejected_by="me")
        self.assertEqual(self.seen[-1]["outcome"], "rejected")
        self.assertEqual(self.seen[-1]["speech"], "Okay, I didn't go ahead with the WhatsApp message.")

    async def test_tasks_without_approval_are_not_announced(self) -> None:
        with patch("orion.tools._openclaw.get_openclaw_client", return_value=_openclaw()):
            await self.runtime.run_tool("check_email", "check email")
        self.assertEqual(self.seen, [])

    async def test_long_details_are_clipped_for_speech(self) -> None:
        verbose = _openclaw(result="word " * 200)
        with patch("orion.tools._openclaw.get_openclaw_client", return_value=verbose):
            task_id = await self._pending_whatsapp()
            await self.runtime.engine.resume_task_after_approval(task_id, approved_by="me")
        self.assertLess(len(self.seen[-1]["speech"]), 320)


class AnnouncerTests(unittest.IsolatedAsyncioTestCase):
    async def test_waits_for_a_pause_before_speaking(self) -> None:
        spoken: list[tuple[float, str]] = []
        busy_until = time.monotonic() + 0.3
        announcer = OutcomeAnnouncer(
            "http://unused",
            speak=lambda text: spoken.append((time.monotonic(), text)),
            is_busy=lambda: time.monotonic() < busy_until,
            pause_poll=0.02,
        )
        await announcer.announce("Done.")
        self.assertEqual(len(spoken), 1)
        self.assertGreaterEqual(spoken[0][0], busy_until)

    async def test_survives_the_app_being_down(self) -> None:
        announcer = OutcomeAnnouncer("http://127.0.0.1:9/none", speak=print, retry_delay=0.05)
        runner = asyncio.create_task(announcer.run())
        await asyncio.sleep(0.3)
        self.assertFalse(runner.done(), "announcer gave up instead of retrying")
        runner.cancel()


class OutcomeStreamTests(unittest.IsolatedAsyncioTestCase):
    """End to end: approve in the 'dashboard' (HTTP), hear it in the 'voice session'."""

    def setUp(self) -> None:
        reset_test_db()
        self.app = make_app(replace(config, enable_scheduler=False))
        self.server = live_server(self.app)
        self.base_url = self.server.__enter__()

    def tearDown(self) -> None:
        self.server.__exit__(None, None, None)

    async def test_approval_is_announced_within_two_seconds(self) -> None:
        runtime = self.app.state.runtime
        heard: asyncio.Queue[str] = asyncio.Queue()
        announcer = OutcomeAnnouncer(
            f"{self.base_url}/api/events/outcomes", speak=heard.put_nowait
        )

        with patch("orion.tools._openclaw.get_openclaw_client", return_value=_openclaw()):
            listener = asyncio.create_task(announcer.run())
            try:
                await asyncio.sleep(0.3)  # let the stream connect
                task = await runtime.run_tool(
                    "send_whatsapp", "WhatsApp Priya", recipient="Priya", message="late"
                )
                async with httpx.AsyncClient(base_url=self.base_url) as client:
                    started = time.monotonic()
                    response = await client.post(
                        f"/api/tasks/{task.id}/approve", json={}, headers=AUTH
                    )
                    self.assertEqual(response.json()["status"], "SUCCEEDED")
                speech = await asyncio.wait_for(heard.get(), timeout=2)
                elapsed = time.monotonic() - started
            finally:
                listener.cancel()

        self.assertEqual(
            speech, "The WhatsApp message you approved went through. Message sent to Priya."
        )
        self.assertLess(elapsed, 2)


if __name__ == "__main__":
    unittest.main()
