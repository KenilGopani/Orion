"""
Persistent event store backed by SQLite via SQLModel.

Implements the same interface as ``EventRecorder`` so it can be
used as a drop-in replacement.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from sqlmodel import col, select

from orion.core.models import RuntimeEvent
from orion.db.models import EventRecord
from orion.db.session import get_session

logger = logging.getLogger("orion.events")

Subscriber = Callable[[RuntimeEvent], None]


class PersistentEventStore:
    """SQLite-backed event store with the same interface as EventRecorder.

    In-process subscribers are notified after each event is committed, so the
    app can push updates (e.g. approval outcomes) without polling the database.
    """

    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []

    def subscribe(self, callback: Subscriber) -> Callable[[], None]:
        """Call ``callback`` for every new event; returns an unsubscribe function."""
        self._subscribers.append(callback)
        return lambda: self._subscribers.remove(callback)

    def record(
        self,
        task_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> RuntimeEvent:
        event = RuntimeEvent(
            task_id=task_id,
            event_type=event_type,
            payload=payload or {},
        )
        rec = EventRecord(
            id=event.id,
            task_id=event.task_id,
            event_type=event.event_type,
            payload=json.dumps(event.payload, default=str),
            created_at=event.timestamp,
        )
        with get_session() as session:
            session.add(rec)
            session.commit()
        for callback in list(self._subscribers):
            try:
                callback(event)
            except Exception:  # a broken listener must never break the engine
                logger.exception("Event subscriber failed for %s", event.event_type)
        return event

    def list_events(self, task_id: str) -> list[RuntimeEvent]:
        with get_session() as session:
            recs = list(
                session.exec(
                    select(EventRecord)
                    .where(EventRecord.task_id == task_id)
                    .order_by(col(EventRecord.created_at))
                )
            )
            return [
                RuntimeEvent(
                    id=rec.id,
                    task_id=rec.task_id,
                    event_type=rec.event_type,
                    timestamp=rec.created_at,
                    payload=json.loads(rec.payload) if rec.payload else {},
                )
                for rec in recs
            ]
