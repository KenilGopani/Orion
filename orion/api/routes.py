from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from orion.core.engine import ExecutionEngine
from orion.core.models import TaskStatus


class CreateTaskRequest(BaseModel):
    user_intent: str


class ApproveTaskRequest(BaseModel):
    approved_by: str = "human_operator"


def build_routes(engine: ExecutionEngine, store: Any, events: Any):
    router = APIRouter()

    # ── Tasks ─────────────────────────────────────────────────────

    @router.post("/tasks")
    async def create_task(request: CreateTaskRequest):
        return await engine.create_task(request.user_intent)

    @router.get("/tasks/{task_id}")
    def get_task(task_id: str):
        task = store.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        return task

    @router.get("/tasks")
    def list_tasks():
        return store.list_tasks()

    # ── Approvals ─────────────────────────────────────────────────

    @router.post("/tasks/{task_id}/approve")
    async def approve_task(task_id: str, request: ApproveTaskRequest):
        try:
            return await engine.resume_task_after_approval(task_id, request.approved_by)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/tasks/{task_id}/reject")
    async def reject_task(task_id: str):
        """Reject a pending approval — marks the task as FAILED."""
        task = store.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        if task.status != TaskStatus.AWAITING_APPROVAL:
            raise HTTPException(
                status_code=400,
                detail=f"Task {task_id} is not awaiting approval (status: {task.status})",
            )
        updated = store.update_task_status(
            task_id, TaskStatus.FAILED, error="Rejected by user"
        )
        events.record(task_id, "task_rejected", {"rejected_by": "dashboard_user"})
        return updated

    # ── Events & Streaming ────────────────────────────────────────

    @router.get("/tasks/{task_id}/events")
    def list_task_events(task_id: str):
        task = store.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        return events.list_events(task_id)

    @router.get("/tasks/{task_id}/stream")
    async def stream_task_events(task_id: str):
        """SSE stream of task events — pushes new events in real time."""
        task = store.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        async def event_generator():
            last_seen = 0
            while True:
                all_events = events.list_events(task_id)
                new_events = all_events[last_seen:]
                for event in new_events:
                    yield f"data: {event.model_dump_json()}\n\n"
                    last_seen += 1
                # Stop streaming if task has reached a terminal state
                current = store.get_task(task_id)
                if current and current.status in (
                    TaskStatus.SUCCEEDED,
                    TaskStatus.FAILED,
                    TaskStatus.CANCELLED,
                ):
                    break
                await asyncio.sleep(0.5)

        return StreamingResponse(
            event_generator(), media_type="text/event-stream"
        )

    # ── Conversations ─────────────────────────────────────────────

    @router.get("/conversations")
    def list_conversations():
        """Return recent conversation messages across all sessions."""
        try:
            from sqlmodel import select
            from orion.db.models import ConversationMessage
            from orion.db.session import get_session

            with get_session() as session:
                messages = list(
                    session.exec(
                        select(ConversationMessage)
                        .order_by(
                            ConversationMessage.timestamp.desc()  # type: ignore[union-attr]
                        )
                        .limit(50)
                    )
                )
                # Return in chronological order
                messages.reverse()
                return [
                    {
                        "id": m.id,
                        "session_id": m.session_id,
                        "role": m.role,
                        "content": m.content,
                        "timestamp": m.timestamp.isoformat(),
                    }
                    for m in messages
                ]
        except Exception:
            return []

    # ── Scheduler ─────────────────────────────────────────────────

    @router.get("/scheduler/jobs")
    def list_scheduler_jobs():
        """Return the list of configured scheduler jobs and their status/next run time."""
        from orion.config import config
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger

        jobs_info = []
        temp_sched = AsyncIOScheduler()

        try:
            # Register both jobs with their configured trigger times to compute next_run_time
            h_mb, m_mb = map(int, config.morning_briefing_time.split(":"))
            temp_sched.add_job(lambda: None, CronTrigger(hour=h_mb, minute=m_mb), id="morning_briefing")

            h_ed, m_ed = map(int, config.email_digest_time.split(":"))
            temp_sched.add_job(lambda: None, CronTrigger(hour=h_ed, minute=m_ed), id="email_digest")

            # Start to calculate next_run_time
            temp_sched.start()

            for job_id, is_enabled, time_str in [
                ("morning_briefing", config.morning_briefing_enabled, config.morning_briefing_time),
                ("email_digest", config.email_digest_enabled, config.email_digest_time),
            ]:
                job = temp_sched.get_job(job_id)
                next_run = None
                if job and config.enable_scheduler and is_enabled:
                    next_run = job.next_run_time.isoformat() if job.next_run_time else None

                jobs_info.append({
                    "id": job_id,
                    "name": job_id.replace("_", " ").title(),
                    "schedule": time_str,
                    "enabled": is_enabled,
                    "next_run": next_run,
                })
        finally:
            try:
                temp_sched.shutdown()
            except Exception:
                pass

        return jobs_info

    # ── Health ────────────────────────────────────────────────────

    @router.get("/health")
    async def health():
        from bridge import get_openclaw_client
        from orion.config import config

        openclaw_ok = False
        try:
            client = get_openclaw_client()
            openclaw_ok = await client.health_check()
        except Exception:
            pass

        return {
            "status": "ok",
            "dev_mode": config.dev_mode,
            "mock_openclaw": config.mock_openclaw,
            "dependencies": {
                "openclaw": openclaw_ok,
            },
            "providers": {
                "stt": config.stt_provider,
                "llm": config.llm_provider,
                "tts": config.tts_provider,
            },
        }

    return router
