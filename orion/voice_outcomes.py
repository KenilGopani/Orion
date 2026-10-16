"""
Tell the user what happened to the actions they approved.

A voice turn ends at "…waiting for your approval". The approval happens later
in the dashboard, so the voice session subscribes to the app's outcome stream
(``GET /api/events/outcomes``, server-sent events) and speaks each outcome at
the next pause.

This module knows nothing about LiveKit: it takes a ``speak`` callback and an
``is_busy`` check, so it can be tested, or driven from a terminal, without
audio.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from collections.abc import Awaitable, Callable

import httpx

logger = logging.getLogger("orion.voice.outcomes")

Speak = Callable[[str], Awaitable[None] | None]


class OutcomeAnnouncer:
    """Streams approval outcomes from the app and speaks them at a pause."""

    def __init__(
        self,
        url: str,
        speak: Speak,
        is_busy: Callable[[], bool] = lambda: False,
        *,
        pause_poll: float = 0.2,
        retry_delay: float = 2.0,
    ) -> None:
        self.url = url
        self._speak = speak
        self._is_busy = is_busy
        self._pause_poll = pause_poll
        self._retry_delay = retry_delay

    async def run(self) -> None:
        """Listen until cancelled, reconnecting if the app restarts."""
        while True:
            try:
                await self._listen()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — never let this kill the voice session
                logger.debug("Outcome stream unavailable (%s); retrying.", exc)
            await asyncio.sleep(self._retry_delay)

    async def _listen(self) -> None:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10, read=None)) as client:
            async with client.stream("GET", self.url) as response:
                response.raise_for_status()
                logger.info("Listening for approval outcomes at %s", self.url)
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        await self.announce(json.loads(line[5:])["speech"])

    async def announce(self, text: str) -> None:
        """Speak ``text`` once neither the user nor the agent is talking."""
        while self._is_busy():
            await asyncio.sleep(self._pause_poll)
        result = self._speak(text)
        if inspect.isawaitable(result):
            await result
