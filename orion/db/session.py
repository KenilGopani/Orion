"""
Database session manager — SQLite via SQLModel.

Creates the database file at ``~/.orion/orion.db`` and provides
a session factory for the persistent stores.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

logger = logging.getLogger("orion.db")

# ── Database path ─────────────────────────────────────────────────────────────

DB_DIR = Path.home() / ".orion"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "orion.db"

DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, echo=False)


# ── Public API ────────────────────────────────────────────────────────────────

def init_db() -> None:
    """Create all tables if they don't already exist."""
    # Import models so SQLModel discovers them before create_all
    import orion.db.models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    logger.info("Database initialised at %s", DB_PATH)


def get_session() -> Session:
    """Return a new SQLModel session (caller must close it)."""
    return Session(engine)
