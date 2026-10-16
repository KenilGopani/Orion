"""
Shared test fixtures — sets up an in-memory SQLite database so tests
never touch the production database at ``~/.orion/orion.db``.
"""

from __future__ import annotations

import dotenv

# Keep a developer's .env out of tests: disable loading before any Orion import.
# (Only load_dotenv is replaced; libraries such as the MCP SDK need the rest.)
dotenv.load_dotenv = lambda *args, **kwargs: False

# These imports must follow the patch above, hence the E402 waivers.
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import SQLModel, create_engine  # noqa: E402

import orion.db.session as db_session  # noqa: E402
import orion.db.models  # noqa: E402,F401 — register table metadata

# Replace the engine with an in-memory SQLite for tests
# StaticPool shares one connection, so API routes run in worker threads see the
# same in-memory database as the test itself.
_test_engine = create_engine(
    "sqlite://",
    echo=False,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
db_session.engine = _test_engine


def reset_test_db() -> None:
    """Drop and recreate all tables — gives each test a clean slate."""
    SQLModel.metadata.drop_all(_test_engine)
    SQLModel.metadata.create_all(_test_engine)


# ── App helpers ───────────────────────────────────────────────────────────────

#: Install token used by test apps, so tests never read or write ~/.orion/api-token.
TEST_TOKEN = "test-token"
AUTH = {"X-Orion-Token": TEST_TOKEN}


def make_app(cfg=None, **kwargs):
    """An Orion app for tests: no OpenClaw probe, a fixed install token."""
    from orion.app import create_app

    kwargs.setdefault("check_openclaw", False)
    kwargs.setdefault("api_token", TEST_TOKEN)
    return create_app(cfg, **kwargs)


def local_client(app):
    """A TestClient that sends a loopback Host header, as a real browser would."""
    from fastapi.testclient import TestClient

    return TestClient(app, base_url="http://127.0.0.1:8000")
