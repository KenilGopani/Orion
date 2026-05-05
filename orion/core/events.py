from __future__ import annotations

from collections import defaultdict
from threading import RLock
from typing import Any

from orion.core.models import RuntimeEvent


class EventRecorder:
    """Append-only runtime event stream keyed by task ID."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._events_by_task: dict[str, list[RuntimeEvent]] = defaultdict(list)

    def record(self, task_id: str, event_type: str, payload: dict[str, Any] | None = None) -> RuntimeEvent:
        with self._lock:
            event = RuntimeEvent(task_id=task_id, event_type=event_type, payload=payload or {})
            self._events_by_task[task_id].append(event)
            return event

    def list_events(self, task_id: str) -> list[RuntimeEvent]:
        with self._lock:
            return list(self._events_by_task.get(task_id, []))
