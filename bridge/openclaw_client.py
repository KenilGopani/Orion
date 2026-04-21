"""
OpenClaw Bridge Client
======================
Async HTTP client that communicates with the OpenClaw gateway daemon.

OpenClaw exposes OpenAI-compatible endpoints on port 18789 by default.
We use ``/v1/chat/completions`` to send natural-language tasks and
receive the agent's response.

Implements retry logic, timeout handling, and response normalisation
so every return value is safe for TTS playback.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from bridge.response_parser import clean_for_tts

logger = logging.getLogger("orion.bridge")

# Retry policy
_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 2  # seconds


class OpenClawClient:
    """Thin async wrapper around the OpenClaw gateway REST API."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:18789",
        api_token: str = "",
        timeout: int = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=httpx.Timeout(timeout, connect=10),
            follow_redirects=True,
        )

    # ── public API ────────────────────────────────────────────────

    async def send_task(self, task: str, context: dict[str, Any] | None = None) -> dict[str, str]:
        """
        Send a natural-language task to the OpenClaw agent.

        Uses the OpenAI-compatible ``/v1/chat/completions`` endpoint so the
        gateway routes the message to the configured default agent, which
        has access to all installed skills (email, messaging, browser, etc.).

        Returns
        -------
        dict
            ``{"status": "success"|"error", "result": "<TTS-safe string>"}``
        """
        messages = [
            {
                "role": "system",
                "content": (
                    "You are executing a task on behalf of Orion, "
                    "a voice assistant. Execute the user's request using your "
                    "available tools and skills. Return a brief, natural-language "
                    "summary of the outcome — no markdown, no code blocks, no "
                    "bullet points. Speak as though reporting to someone verbally."
                ),
            },
            {"role": "user", "content": task},
        ]

        if context:
            messages[0]["content"] += f"\n\nAdditional context: {context}"

        payload = {
            "model": "openclaw",
            "messages": messages,
        }

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp = await self._client.post("/v1/chat/completions", json=payload)
                resp.raise_for_status()
                data = resp.json()

                # Extract the assistant message from standard OpenAI response shape
                raw_text = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )

                if not raw_text:
                    return {
                        "status": "error",
                        "result": "OpenClaw completed the task but returned no details, sir.",
                    }

                return {"status": "success", "result": clean_for_tts(raw_text)}

            except httpx.TimeoutException:
                if attempt == _MAX_RETRIES:
                    logger.error("OpenClaw timed out after %d attempts for task: %s", _MAX_RETRIES, task)
                    return {
                        "status": "error",
                        "result": "I'm afraid OpenClaw didn't respond in time, sir. The daemon may be under heavy load.",
                    }
                logger.warning("OpenClaw timeout (attempt %d/%d), retrying…", attempt, _MAX_RETRIES)

            except httpx.ConnectError:
                logger.error("Cannot reach OpenClaw at %s", self.base_url)
                return {
                    "status": "error",
                    "result": (
                        "I'm afraid OpenClaw isn't responding, sir. "
                        "Please ensure the daemon is running with: openclaw gateway"
                    ),
                }

            except httpx.HTTPStatusError as exc:
                logger.error("OpenClaw HTTP %d: %s", exc.response.status_code, exc.response.text[:200])
                return {
                    "status": "error",
                    "result": f"OpenClaw returned an error, sir. Status code {exc.response.status_code}.",
                }

            except Exception as exc:
                logger.exception("Unexpected error communicating with OpenClaw: %s", exc)
                return {
                    "status": "error",
                    "result": "I encountered an unexpected error reaching OpenClaw, sir.",
                }

            # Exponential backoff between retries
            await asyncio.sleep(_RETRY_BACKOFF_BASE ** attempt)

        # Should not reach here, but just in case
        return {"status": "error", "result": "Something went wrong with the OpenClaw request, sir."}

    async def health_check(self) -> bool:
        """
        Return ``True`` if the OpenClaw gateway is reachable.

        Probes ``/v1/models`` which is a lightweight read-only endpoint
        that every OpenClaw gateway exposes.
        """
        try:
            resp = await self._client.get("/v1/models")
            return resp.status_code == 200
        except Exception:
            return False

    async def list_skills(self) -> list[str]:
        """
        Return available model/agent identifiers from the gateway.

        OpenClaw surfaces agents as "models" via ``/v1/models``.
        """
        try:
            resp = await self._client.get("/v1/models")
            resp.raise_for_status()
            data = resp.json()
            return [m.get("id", "unknown") for m in data.get("data", [])]
        except Exception as exc:
            logger.warning("Could not list OpenClaw models: %s", exc)
            return []

    async def close(self) -> None:
        """Shut down the underlying HTTP client."""
        await self._client.aclose()
