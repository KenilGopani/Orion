from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from orion.core.engine import ExecutionEngine
from orion.core.events import EventRecorder
from orion.core.store import InMemoryTaskStore


class CreateTaskRequest(BaseModel):
    user_intent: str


class ApproveTaskRequest(BaseModel):
    approved_by: str = "human_operator"


def build_routes(engine: ExecutionEngine, store: InMemoryTaskStore, events: EventRecorder):
    router = APIRouter()

    @router.post("/tasks")
    def create_task(request: CreateTaskRequest):
        return engine.create_task(request.user_intent)

    @router.get("/tasks/{task_id}")
    def get_task(task_id: str):
        task = store.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        return task

    @router.get("/tasks")
    def list_tasks():
        return store.list_tasks()

    @router.post("/tasks/{task_id}/approve")
    def approve_task(task_id: str, request: ApproveTaskRequest):
        try:
            return engine.resume_task_after_approval(task_id, request.approved_by)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/tasks/{task_id}/events")
    def list_task_events(task_id: str):
        task = store.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        return events.list_events(task_id)

    return router
