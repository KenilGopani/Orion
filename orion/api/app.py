from __future__ import annotations

from fastapi import FastAPI

from orion.api.routes import build_routes
from orion.core.approvals import ApprovalGate
from orion.core.engine import ExecutionEngine, default_registry
from orion.core.events import EventRecorder
from orion.core.store import InMemoryTaskStore


def create_app() -> FastAPI:
    store = InMemoryTaskStore()
    events = EventRecorder()
    registry = default_registry()
    approval_gate = ApprovalGate(store)
    engine = ExecutionEngine(
        store=store,
        events=events,
        registry=registry,
        approval_gate=approval_gate,
    )

    app = FastAPI(title="Orion Runtime API", version="0.1.0")
    app.include_router(build_routes(engine, store, events))
    return app


app = create_app()
