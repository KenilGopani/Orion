from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from orion.api.routes import build_routes
from orion.core.runtime import engine, events, store


def create_app() -> FastAPI:
    app = FastAPI(title="Orion Runtime API", version="0.1.0")

    # CORS — allow dashboard dev server and common origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(build_routes(engine, store, events))
    return app


app = create_app()
