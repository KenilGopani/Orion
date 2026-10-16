"""
Tests for the OrionScheduler service and the /scheduler/jobs API endpoint.
"""

from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock


from tests.conftest import local_client, make_app, reset_test_db

from orion.config import config
from orion.services.scheduler import OrionScheduler


class SchedulerServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        reset_test_db()
        self.mock_engine = MagicMock()
        self.mock_engine.create_task = AsyncMock()
        self.scheduler = OrionScheduler(self.mock_engine)

    def tearDown(self) -> None:
        self.scheduler.shutdown()

    async def test_jobs_registered_when_enabled(self) -> None:
        """Scheduler should add jobs only when enabled in config."""
        mock_config = MagicMock()
        mock_config.morning_briefing_enabled = True
        mock_config.morning_briefing_time = "08:00"
        mock_config.email_digest_enabled = False
        mock_config.email_digest_time = "20:00"

        self.scheduler.start(mock_config)

        jobs = self.scheduler.list_jobs()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["id"], "morning_briefing")

    async def test_jobs_disabled_when_config_disabled(self) -> None:
        """Scheduler should register no jobs if all are disabled."""
        mock_config = MagicMock()
        mock_config.morning_briefing_enabled = False
        mock_config.morning_briefing_time = "08:00"
        mock_config.email_digest_enabled = False
        mock_config.email_digest_time = "20:00"

        self.scheduler.start(mock_config)

        jobs = self.scheduler.list_jobs()
        self.assertEqual(len(jobs), 0)

    async def test_morning_briefing_callback(self) -> None:
        """Callback for morning briefing should create the correct task in engine."""
        await self.scheduler._morning_briefing()
        self.mock_engine.create_task.assert_awaited_once_with(
            "Check my email for urgent messages and check my calendar for today."
        )

    async def test_email_digest_callback(self) -> None:
        """Callback for email digest should create the correct task in engine."""
        await self.scheduler._email_digest()
        self.mock_engine.create_task.assert_awaited_once_with(
            "Summarize my inbox from the last 24 hours."
        )

    def test_api_endpoint_reports_live_scheduler(self) -> None:
        """GET /api/scheduler/jobs lists every configured job; next_run comes
        from the scheduler running inside the app, so only enabled jobs have one."""
        cfg = replace(
            config,
            enable_scheduler=True,
            morning_briefing_enabled=True,
            morning_briefing_time="07:30",
            email_digest_enabled=False,
            email_digest_time="18:30",
        )
        app = make_app(cfg)

        with local_client(app) as client:
            self.assertIsNotNone(app.state.runtime.scheduler)
            response = client.get("/api/scheduler/jobs")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 2)

        mb_job = next(j for j in data if j["id"] == "morning_briefing")
        self.assertEqual(mb_job["name"], "Morning Briefing")
        self.assertEqual(mb_job["schedule"], "07:30")
        self.assertTrue(mb_job["enabled"])
        self.assertIsNotNone(mb_job["next_run"])

        ed_job = next(j for j in data if j["id"] == "email_digest")
        self.assertEqual(ed_job["name"], "Email Digest")
        self.assertEqual(ed_job["schedule"], "18:30")
        self.assertFalse(ed_job["enabled"])
        self.assertIsNone(ed_job["next_run"])

        # The lifespan stopped the scheduler on shutdown.
        self.assertIsNone(app.state.runtime.scheduler)

    def test_api_endpoint_without_scheduler(self) -> None:
        """With the scheduler off, jobs are listed but none has a next run."""
        cfg = replace(config, enable_scheduler=False, morning_briefing_enabled=True)
        with local_client(make_app(cfg)) as client:
            data = client.get("/api/scheduler/jobs").json()
        self.assertTrue(all(job["next_run"] is None for job in data))


if __name__ == "__main__":
    unittest.main()
