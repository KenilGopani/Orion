from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from orion.api.security import require_token
from orion.core.models import RuntimeEvent, TaskStatus
from orion.services.outcomes import outcome_for
from orion.services.scheduler import describe_jobs

if TYPE_CHECKING:
    from orion.core.runtime import Runtime


#: Seconds between SSE keep-alive comments on idle streams.
OUTCOME_KEEPALIVE = 15


class CreateTaskRequest(BaseModel):
    user_intent: str


class ApproveTaskRequest(BaseModel):
    approved_by: str = "human_operator"


class RejectTaskRequest(BaseModel):
    rejected_by: str = "human_operator"


def build_routes(runtime: Runtime, api_token: str) -> APIRouter:
    router = APIRouter()
    engine, store, events = runtime.engine, runtime.store, runtime.events
    # Every route that changes state requires the install token (see security.py).
    authorized = [Depends(require_token(api_token))]

    # ── Auth ──────────────────────────────────────────────────────

    @router.get("/auth/token")
    def get_token():
        """Hand the install token to the dashboard.

        Safe to expose because only loopback Host headers reach this app and
        cross-origin pages can't read the response (no CORS grant).
        """
        return {"token": api_token}

    # ── Tasks ─────────────────────────────────────────────────────

    @router.post("/tasks", dependencies=authorized)
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

    @router.post("/tasks/{task_id}/approve", dependencies=authorized)
    async def approve_task(task_id: str, request: ApproveTaskRequest):
        try:
            return await engine.resume_task_after_approval(task_id, request.approved_by)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/tasks/{task_id}/reject", dependencies=authorized)
    async def reject_task(task_id: str, request: RejectTaskRequest | None = None):
        """Reject a pending approval — the step is skipped and the task FAILS."""
        rejected_by = request.rejected_by if request else "human_operator"
        try:
            return engine.reject_task(task_id, rejected_by)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # ── Events & Streaming ────────────────────────────────────────

    @router.get("/tasks/{task_id}/events")
    def list_task_events(task_id: str):
        task = store.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        return events.list_events(task_id)

    @router.get("/events/outcomes")
    async def stream_outcomes():
        """SSE stream of approval outcomes, each with a sentence to speak.

        The voice agent subscribes so it can say "The WhatsApp message you
        approved went through." Only outcomes that happen after connecting are
        sent; earlier ones are in the dashboard.
        """
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def on_event(event: RuntimeEvent) -> None:
            outcome = outcome_for(event, runtime)
            if outcome:
                # Events may be recorded off the event loop (e.g. a sync route
                # in the threadpool); hand the outcome over thread-safely.
                loop.call_soon_threadsafe(queue.put_nowait, outcome)

        unsubscribe = events.subscribe(on_event)

        async def outcome_stream():
            try:
                yield ": connected\n\n"
                while True:
                    try:
                        outcome = await asyncio.wait_for(queue.get(), timeout=OUTCOME_KEEPALIVE)
                    except asyncio.TimeoutError:
                        yield ": keep-alive\n\n"
                        continue
                    yield f"data: {json.dumps(outcome)}\n\n"
            finally:
                unsubscribe()

        return StreamingResponse(outcome_stream(), media_type="text/event-stream")

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
            from sqlmodel import col, select
            from orion.db.models import ConversationMessage
            from orion.db.session import get_session

            with get_session() as session:
                messages = list(
                    session.exec(
                        select(ConversationMessage)
                        .order_by(
                            col(ConversationMessage.timestamp).desc()
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
        """Configured scheduler jobs, with next run times from the live scheduler."""
        return describe_jobs(runtime.config, runtime.scheduler)

    # ── Health ────────────────────────────────────────────────────

    @router.get("/health")
    async def health():
        from bridge import get_openclaw_client

        config = runtime.config
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
