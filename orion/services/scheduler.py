"""
Scheduler service — APScheduler integration for proactive behaviors.
"""

from __future__ import annotations

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger("orion.scheduler")


class OrionScheduler:
    """Orion system scheduler for managing proactive background tasks."""

    def __init__(self, engine):
        self.scheduler = AsyncIOScheduler()
        self.engine = engine

    def start(self, config) -> None:
        """Register enabled jobs and start the scheduler."""
        logger.info("Starting Orion scheduler...")
        if config.morning_briefing_enabled:
            h, m = map(int, config.morning_briefing_time.split(":"))
            self.scheduler.add_job(
                self._morning_briefing,
                CronTrigger(hour=h, minute=m),
                id="morning_briefing",
            )
            logger.info(
                "Registered 'morning_briefing' job to run at %s",
                config.morning_briefing_time,
            )
        if config.email_digest_enabled:
            h, m = map(int, config.email_digest_time.split(":"))
            self.scheduler.add_job(
                self._email_digest,
                CronTrigger(hour=h, minute=m),
                id="email_digest",
            )
            logger.info(
                "Registered 'email_digest' job to run at %s",
                config.email_digest_time,
            )
        self.scheduler.start()
        logger.info("Orion scheduler started.")

    def list_jobs(self) -> list[dict]:
        """Return a list of all active jobs and their next run times."""
        return [
            {
                "id": j.id,
                "next_run": j.next_run_time.isoformat()
                if j.next_run_time
                else None,
            }
            for j in self.scheduler.get_jobs()
        ]

    async def _morning_briefing(self) -> None:
        """Task callback for morning briefing."""
        logger.info("Triggering scheduled morning briefing...")
        await self.engine.create_task(
            "Check my email for urgent messages and check my calendar for today."
        )

    async def _email_digest(self) -> None:
        """Task callback for email digest."""
        logger.info("Triggering scheduled email digest...")
        await self.engine.create_task(
            "Summarize my inbox from the last 24 hours."
        )
