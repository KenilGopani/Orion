"""
Memory service — persistent fact storage for Orion.

Provides remember/recall/forget operations backed by SQLite.
All methods are synchronous (no async) since they use short-lived
SQLModel sessions.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlmodel import select

from orion.db.models import MemoryRecord
from orion.db.session import get_session

logger = logging.getLogger("orion.memory")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MemoryService:
    """CRUD service for Orion's long-term memory."""

    # ── Remember ──────────────────────────────────────────────────

    def remember(self, key: str, value: str, source: str = "voice") -> MemoryRecord:
        """Store or update a fact. Upserts by key (case-insensitive)."""
        normalised_key = key.strip().lower()

        with get_session() as session:
            # Check for existing record with same key
            existing = session.exec(
                select(MemoryRecord).where(MemoryRecord.key == normalised_key)
            ).first()

            if existing:
                existing.value = value
                existing.source = source
                existing.updated_at = _utc_now()
                session.add(existing)
                session.commit()
                session.refresh(existing)
                logger.info("Updated memory: %s = %s", normalised_key, value[:50])
                return existing

            record = MemoryRecord(
                key=normalised_key,
                value=value,
                source=source,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            logger.info("Stored new memory: %s = %s", normalised_key, value[:50])
            return record

    # ── Recall ────────────────────────────────────────────────────

    def recall(self, topic: str) -> list[MemoryRecord]:
        """Search memories by topic using LIKE matching.

        Returns all records whose key contains the topic substring.
        """
        normalised = topic.strip().lower()

        with get_session() as session:
            results = list(
                session.exec(
                    select(MemoryRecord).where(
                        MemoryRecord.key.contains(normalised)  # type: ignore[union-attr]
                    )
                )
            )
            return results

    # ── Forget ────────────────────────────────────────────────────

    def forget(self, key: str) -> bool:
        """Delete a memory by key. Returns True if found and deleted."""
        normalised = key.strip().lower()

        with get_session() as session:
            # Try exact match first
            record = session.exec(
                select(MemoryRecord).where(MemoryRecord.key == normalised)
            ).first()

            if not record:
                # Try LIKE match
                record = session.exec(
                    select(MemoryRecord).where(
                        MemoryRecord.key.contains(normalised)  # type: ignore[union-attr]
                    )
                ).first()

            if record:
                session.delete(record)
                session.commit()
                logger.info("Forgot memory: %s", normalised)
                return True

            logger.info("Nothing to forget for: %s", normalised)
            return False

    # ── Bulk access ───────────────────────────────────────────────

    def get_all(self) -> list[MemoryRecord]:
        """Return all stored memories, ordered by most recent first."""
        with get_session() as session:
            return list(
                session.exec(
                    select(MemoryRecord).order_by(
                        MemoryRecord.updated_at.desc()  # type: ignore[union-attr]
                    )
                )
            )

    # ── Context formatting ────────────────────────────────────────

    def format_for_context(self) -> str:
        """Format all memories as a bullet list for the LLM system prompt.

        Returns an empty string if there are no memories.
        """
        memories = self.get_all()
        if not memories:
            return ""

        lines = [f"- {m.key}: {m.value}" for m in memories]
        return "\n".join(lines)


# Module-level singleton
memory_service = MemoryService()
