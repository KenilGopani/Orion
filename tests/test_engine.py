"""
Engine and approval-gate behaviour that the adapter tests don't cover:
rejection, failure reporting, gate coverage and timestamp round-tripping.
"""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from tests.conftest import reset_test_db

from orion.core.engine import PlannedStep
from orion.core.models import StepStatus, TaskStatus
from orion.core.runtime import build_runtime
from orion.tools._gated import describe_outcome

runtime = build_runtime()
engine, events, registry, store = runtime.engine, runtime.events, runtime.registry, runtime.store
run_tool = runtime.run_tool


def _mock_openclaw(status: str = "success", result: str = "done") -> AsyncMock:
    client = AsyncMock()
    client.send_task.return_value = {"status": status, "result": result}
    return client


class RejectionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        reset_test_db()

    async def test_reject_closes_approval_and_skips_step(self) -> None:
        client = _mock_openclaw()
        with patch("orion.core.runtime.get_openclaw_client", return_value=client):
            task = await run_tool("openclaw_send_email", "email", to="a@b.c", subject="s", body="b")
            rejected = engine.reject_task(task.id, rejected_by="tester")

        self.assertEqual(rejected.status, TaskStatus.FAILED)
        self.assertEqual(rejected.steps[0].status, StepStatus.SKIPPED)
        self.assertIsNone(store.get_latest_pending_approval(task.id))
        approval = store.list_approval_requests(task.id)[0]
        self.assertIsNotNone(approval.rejected_at)
        self.assertIsNone(approval.approved_at)
        self.assertIn("task_rejected", [e.event_type for e in events.list_events(task.id)])
        client.send_task.assert_not_called()

    async def test_rejected_task_cannot_then_be_approved(self) -> None:
        with patch("orion.core.runtime.get_openclaw_client", return_value=_mock_openclaw()):
            task = await run_tool("openclaw_run_command", "rm", command="rm -rf /tmp/x")
            engine.reject_task(task.id, rejected_by="tester")
            with self.assertRaises(ValueError):
                await engine.resume_task_after_approval(task.id, approved_by="tester")

    async def test_reject_requires_pending_approval(self) -> None:
        task = await engine.create_task("echo something")
        with self.assertRaises(ValueError):
            engine.reject_task(task.id, rejected_by="tester")


class FailureTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        reset_test_db()

    async def test_unknown_tool_fails_task_instead_of_leaving_it_running(self) -> None:
        task = await engine.create_task_with_steps(
            "bad", [PlannedStep(name="x", description="", tool_name="does_not_exist")]
        )
        self.assertEqual(task.status, TaskStatus.FAILED)
        self.assertEqual(task.steps[0].status, StepStatus.FAILED)

    async def test_failed_tool_is_never_described_as_success(self) -> None:
        with patch(
            "orion.core.runtime.get_openclaw_client",
            return_value=_mock_openclaw(status="error", result="Disk full."),
        ):
            task = await run_tool("openclaw_write_file", "write", path="/tmp/a", content="b")
            task = await engine.resume_task_after_approval(task.id, approved_by="tester")

        self.assertEqual(task.status, TaskStatus.FAILED)
        spoken = describe_outcome(task, "Writing the file")
        self.assertIn("didn't go through", spoken)
        self.assertIn("Disk full.", spoken)

    async def test_awaiting_approval_message_is_not_technical(self) -> None:
        with patch("orion.core.runtime.get_openclaw_client", return_value=_mock_openclaw()):
            task = await run_tool("openclaw_send_slack", "slack", channel="#x", message="hi")
        spoken = describe_outcome(task, "The Slack message")
        self.assertNotIn("POST", spoken)
        self.assertNotIn(task.id, spoken)


class GateCoverageTests(unittest.TestCase):
    def test_tools_that_act_on_the_world_require_approval(self) -> None:
        for name in (
            "openclaw_send_email",
            "openclaw_send_whatsapp",
            "openclaw_send_telegram",
            "openclaw_send_slack",
            "openclaw_create_event",
            "openclaw_reschedule_event",
            "openclaw_write_file",
            "openclaw_run_command",
            "openclaw_run_code",
        ):
            with self.subTest(tool=name):
                self.assertTrue(registry.get(name).requires_approval)


class TimestampTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_test_db()

    def test_timestamps_round_trip_as_utc_aware(self) -> None:
        task = store.create_task("x")
        loaded = store.get_task(task.id)
        assert loaded is not None
        self.assertIsNotNone(loaded.created_at.tzinfo)
        self.assertEqual(loaded.created_at, task.created_at)
        # Serialised with an offset, so browsers don't read it as local time.
        self.assertRegex(loaded.model_dump()["created_at"].isoformat(), r"\+00:00$")


class MemoryForgetTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_test_db()

    def test_ambiguous_forget_deletes_nothing(self) -> None:
        from orion.services.memory import memory_service

        memory_service.remember("standup time", "10am")
        memory_service.remember("standup room", "Blue")
        self.assertFalse(memory_service.forget("standup"))
        self.assertEqual(len(memory_service.get_all()), 2)
        self.assertTrue(memory_service.forget("standup room"))
        self.assertEqual(len(memory_service.get_all()), 1)

    def test_recall_matches_values_too(self) -> None:
        from orion.services.memory import memory_service

        memory_service.remember("priya email", "priya@example.com")
        memory_service.remember("dentist", "Dr. Rao on Friday")
        self.assertEqual([m.key for m in memory_service.recall("rao")], ["dentist"])


if __name__ == "__main__":
    unittest.main()
