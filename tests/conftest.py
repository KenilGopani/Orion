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
