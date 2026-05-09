from __future__ import annotations

from fastapi import FastAPI

from orion.api.routes import build_routes
from orion.core.runtime import engine, events, store


def create_app() -> FastAPI:
    app = FastAPI(title="Orion Runtime API", version="0.1.0")
    app.include_router(build_routes(engine, store, events))
    return app


app = create_app()
