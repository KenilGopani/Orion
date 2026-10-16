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

    def shutdown(self) -> None:
        """Stop the scheduler if it is running."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Orion scheduler stopped.")

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


def describe_jobs(config, scheduler: OrionScheduler | None) -> list[dict]:
    """Every configured job, with its next run time from the live scheduler.

    Jobs that are disabled, or configured while the scheduler is off, are still
    listed so the dashboard can show them, with ``next_run`` set to ``None``.
    """
    live = {job["id"]: job["next_run"] for job in scheduler.list_jobs()} if scheduler else {}
    configured = [
        ("morning_briefing", config.morning_briefing_enabled, config.morning_briefing_time),
        ("email_digest", config.email_digest_enabled, config.email_digest_time),
    ]
    return [
        {
            "id": job_id,
            "name": job_id.replace("_", " ").title(),
            "schedule": time_str,
            "enabled": enabled,
            "next_run": live.get(job_id),
        }
        for job_id, enabled, time_str in configured
    ]
