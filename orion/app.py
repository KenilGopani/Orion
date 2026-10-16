"""
The Orion application — one ASGI app, one engine.

    /api/*    REST API used by the dashboard
    /mcp/sse  MCP tools used by the voice agent (SSE transport)
    /         the built dashboard (``make dashboard-build``)

The scheduler starts and stops with the app. Run it with ``orion up``.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from mcp.server.fastmcp import FastMCP

from bridge.openclaw_client import OpenClawClient
from orion.api.routes import build_routes
from orion.api.security import LoopbackHostMiddleware, load_or_create_token
from orion.config import Config, config as default_config
from orion.core.runtime import Runtime, build_runtime
from orion.db.session import DB_DIR, init_db
from orion.openclaw_setup import log_openclaw_safety
from orion.tools._mcp import expose_tools

logger = logging.getLogger("orion.app")

DASHBOARD_DIST = Path(__file__).resolve().parent.parent / "dashboard" / "dist"
TOKEN_PATH = DB_DIR / "api-token"
MCP_MOUNT_PATH = "/mcp"

_DASHBOARD_MISSING = """<!doctype html><meta charset="utf-8"><title>Orion</title>
<body style="font-family:system-ui;max-width:40rem;margin:4rem auto;padding:0 1rem">
<h1>Orion is running</h1>
<p>The dashboard hasn't been built yet. Run <code>make dashboard-build</code>
and reload, or use <code>make dashboard</code> for the dev server.</p>
<p>API: <a href="/api/health">/api/health</a></p></body>"""


def build_mcp(runtime: Runtime) -> FastMCP:
    """Create the MCP server that exposes Orion's tools to the voice agent."""
    mcp = FastMCP(
        name=runtime.config.server_name,
        instructions=(
            "You are Orion, a voice-first AI assistant. "
            "You have access to tools that connect to the OpenClaw daemon "
            "for executing real-world tasks. Be concise and precise."
        ),
    )
    expose_tools(mcp, runtime)
    return mcp


async def _log_openclaw_health(cfg: Config) -> None:
    """Log whether the OpenClaw daemon is reachable at startup.

    Uses its own short-lived client so no pooled connection outlives this
    check (the shared client is created lazily inside request handlers).
    """
    client = OpenClawClient(base_url=cfg.openclaw_url, api_token=cfg.openclaw_token)
    try:
        healthy = await client.health_check()
        skills = await client.list_skills() if healthy else []
    finally:
        await client.close()
    if healthy:
        logger.info("✓ OpenClaw daemon is ONLINE at %s", cfg.openclaw_url)
        if skills:
            logger.info("  Available agents/models: %s", ", ".join(skills))
    else:
        logger.warning(
            "✗ OpenClaw daemon is OFFLINE at %s — tools will return error messages. "
            "Start it with: openclaw gateway --port 18789",
            cfg.openclaw_url,
        )


def create_app(
    cfg: Config | None = None,
    *,
    check_openclaw: bool = True,
    api_token: str | None = None,
) -> FastAPI:
    """Build the Orion app. Constructs exactly one runtime (and engine).

    ``api_token`` defaults to the per-install token in ``~/.orion/api-token``.
    """
    cfg = cfg or default_config
    runtime = build_runtime(cfg)
    token = api_token or load_or_create_token(TOKEN_PATH)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        init_db()
        if cfg.enable_scheduler:
            from orion.services.scheduler import OrionScheduler

            runtime.scheduler = OrionScheduler(runtime.engine)
            runtime.scheduler.start(cfg)
        if check_openclaw:
            await _log_openclaw_health(cfg)
            log_openclaw_safety(cfg)
        try:
            yield
        finally:
            if runtime.scheduler:
                runtime.scheduler.shutdown()
                runtime.scheduler = None

    app = FastAPI(title="Orion", version="1.0.0", lifespan=lifespan)
    app.state.runtime = runtime

    # Only the Vite dev server needs CORS; the built dashboard is same-origin.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Added last, so it runs first: refuse non-loopback Host headers (DNS rebinding).
    app.add_middleware(LoopbackHostMiddleware, allowed_hosts=cfg.allowed_hosts)

    app.include_router(build_routes(runtime, token), prefix="/api")
    # Starlette's Mount sets root_path, which the SSE transport already prefixes
    # onto its message URL; passing mount_path to sse_app() would double it.
    app.mount(MCP_MOUNT_PATH, build_mcp(runtime).sse_app())

    if DASHBOARD_DIST.is_dir():
        app.mount("/", StaticFiles(directory=DASHBOARD_DIST, html=True), name="dashboard")
    else:
        @app.get("/", include_in_schema=False)
        def dashboard_missing() -> HTMLResponse:
            return HTMLResponse(_DASHBOARD_MISSING)

    return app
