"""
Shared test fixtures — sets up an in-memory SQLite database so tests
never touch the production database at ``~/.orion/orion.db``.
"""

from __future__ import annotations

import types
import sys

# Shim dotenv before any Orion imports
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda: None))

from sqlmodel import SQLModel, Session, create_engine

import orion.db.session as db_session
import orion.db.models  # noqa: F401 — register table metadata

# Replace the engine with an in-memory SQLite for tests
_test_engine = create_engine("sqlite://", echo=False)
db_session.engine = _test_engine


def reset_test_db() -> None:
    """Drop and recreate all tables — gives each test a clean slate."""
    SQLModel.metadata.drop_all(_test_engine)
    SQLModel.metadata.create_all(_test_engine)
