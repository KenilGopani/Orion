"""
Tests for the OrionScheduler service and the /scheduler/jobs API endpoint.
"""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from orion.api.app import app
from orion.services.scheduler import OrionScheduler
from tests.conftest import reset_test_db  # noqa: F401


class SchedulerServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        reset_test_db()
        self.mock_engine = MagicMock()
        self.mock_engine.create_task = AsyncMock()
        self.scheduler = OrionScheduler(self.mock_engine)

    def tearDown(self) -> None:
        try:
            self.scheduler.scheduler.shutdown()
        except Exception:
            pass

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

    def test_api_endpoint_structure(self) -> None:
        """API GET /scheduler/jobs endpoint returns all jobs with status and schedule."""
        # Patch configuration values to ensure deterministic results in test
        with patch("orion.config.config") as mock_cfg:
            mock_cfg.enable_scheduler = True
            mock_cfg.morning_briefing_enabled = True
            mock_cfg.morning_briefing_time = "07:30"
            mock_cfg.email_digest_enabled = False
            mock_cfg.email_digest_time = "18:30"

            client = TestClient(app)
            response = client.get("/scheduler/jobs")

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


if __name__ == "__main__":
    unittest.main()
