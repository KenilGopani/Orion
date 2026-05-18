"""
Conversation logging service — persists voice/text exchanges.

Writes each user utterance and assistant response to the
``conversation_log`` table for future context and debugging.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from sqlmodel import select

from orion.db.models import ConversationMessage
from orion.db.session import get_session

logger = logging.getLogger("orion.conversation")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ConversationLogger:
    """Logs conversation messages to SQLite."""

    def __init__(self, session_id: str | None = None) -> None:
        self.session_id = session_id or str(uuid4())

    def log(self, role: str, content: str) -> ConversationMessage:
        """Write a message to the conversation log.

        Args:
            role: "user" or "assistant"
            content: The message content.
        """
        msg = ConversationMessage(
            session_id=self.session_id,
            role=role,
            content=content,
        )
        with get_session() as session:
            session.add(msg)
            session.commit()
            session.refresh(msg)
        logger.debug("Logged %s: %s", role, content[:60])
        return msg

    def get_history(self, limit: int = 50) -> list[ConversationMessage]:
        """Return recent messages for this session."""
        with get_session() as session:
            return list(
                session.exec(
                    select(ConversationMessage)
                    .where(ConversationMessage.session_id == self.session_id)
                    .order_by(ConversationMessage.timestamp.desc())  # type: ignore[union-attr]
                    .limit(limit)
                )
            )

    def get_all_sessions(self) -> list[str]:
        """Return all unique session IDs."""
        with get_session() as session:
            results = session.exec(
                select(ConversationMessage.session_id).distinct()
            )
            return list(results)
