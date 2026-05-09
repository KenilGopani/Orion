from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda: None))

from orion.core.models import TaskStatus
from orion.core.runtime import engine, events, run_runtime_send_whatsapp, store


class RuntimeMessagingAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        store._tasks.clear()  # noqa: SLF001
        store._approvals_by_task.clear()  # noqa: SLF001
        store._approvals_by_id.clear()  # noqa: SLF001
        events._events_by_task.clear()  # noqa: SLF001

    async def test_safe_runtime_task_succeeds(self) -> None:
        task = await engine.create_task("echo this safely")
        self.assertEqual(task.status, TaskStatus.SUCCEEDED)

    async def test_send_whatsapp_requires_approval(self) -> None:
        with patch(
            "orion.core.runtime.openclaw_client.send_task",
            new=AsyncMock(return_value={"status": "success", "result": "delivered"}),
        ):
            task = await run_runtime_send_whatsapp(
                recipient="+15551234567",
                message="This should pause until approved",
            )
            self.assertEqual(task.status, TaskStatus.AWAITING_APPROVAL)

    async def test_send_whatsapp_resumes_after_approval(self) -> None:
        with patch(
            "orion.core.runtime.openclaw_client.send_task",
            new=AsyncMock(return_value={"status": "success", "result": "delivered"}),
        ):
            task = await run_runtime_send_whatsapp(
                recipient="+15551234567",
                message="Approval flow",
            )
            self.assertEqual(task.status, TaskStatus.AWAITING_APPROVAL)

            resumed = await engine.resume_task_after_approval(task.id, approved_by="tester")
            self.assertEqual(resumed.status, TaskStatus.SUCCEEDED)
            event_types = [event.event_type for event in events.list_events(task.id)]
            self.assertIn("approval_required", event_types)
            self.assertIn("approval_granted", event_types)
            self.assertIn("task_succeeded", event_types)


if __name__ == "__main__":
    unittest.main()
