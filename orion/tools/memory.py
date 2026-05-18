"""
Memory tools — remember facts, recall knowledge, forget things.

Routes through the local MemoryService (SQLite-backed) instead of
OpenClaw. For ``remember_this``, a small LLM call extracts a
structured key/value pair from natural language. Falls back to
slugifying the whole fact as the key if the LLM call fails.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger("orion.tools.memory")


def _slugify(text: str) -> str:
    """Convert a sentence to a simple key slug."""
    # Take first ~50 chars, lowercase, strip non-alphanumeric
    cleaned = re.sub(r"[^a-z0-9\s]", "", text.lower().strip())
    words = cleaned.split()[:6]  # Max 6 words for key
    return " ".join(words)


async def _extract_key_value(fact: str) -> tuple[str, str]:
    """Use the planner's LLM to extract key/value from a fact.

    Falls back to slugifying the whole fact if the LLM call fails.
    """
    from orion.config import config

    # In dev mode, use simple heuristic extraction
    if config.dev_mode:
        return _heuristic_extract(fact)

    # Try LLM extraction
    try:
        import httpx
        import json

        from orion.core.planner import _get_api_key, _PROVIDER_URLS, _PROVIDER_MODELS

        api_key = _get_api_key(config.llm_provider)
        if not api_key:
            return _heuristic_extract(fact)

        url = _PROVIDER_URLS.get(config.llm_provider)
        model = _PROVIDER_MODELS.get(config.llm_provider)

        if not url or not model:
            return _heuristic_extract(fact)

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        'Extract a short key and value from this fact. '
                        'Return ONLY JSON: {"key": "...", "value": "..."}\n'
                        'Example: "My gym password is 1234" → '
                        '{"key": "gym password", "value": "1234"}'
                    ),
                },
                {"role": "user", "content": fact},
            ],
            "temperature": 0.0,
        }

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        raw = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )

        # Strip markdown fences
        cleaned = raw.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

        parsed = json.loads(cleaned)
        key = parsed.get("key", "").strip()
        value = parsed.get("value", "").strip()

        if key and value:
            return key, value

    except Exception as exc:
        logger.warning("LLM key extraction failed: %s — using heuristic", exc)

    return _heuristic_extract(fact)


def _heuristic_extract(fact: str) -> tuple[str, str]:
    """Extract key/value from a fact using simple heuristics.

    Patterns handled:
    - "my X is Y"
    - "X is Y"
    - "remember that X"
    """
    lower = fact.lower().strip()

    # "my X is Y" pattern
    match = re.match(r"(?:my\s+)?(.+?)\s+is\s+(.+)", lower)
    if match:
        return match.group(1).strip(), match.group(2).strip()

    # "X: Y" pattern
    if ":" in fact:
        parts = fact.split(":", 1)
        return parts[0].strip().lower(), parts[1].strip()

    # Fallback: slugify whole fact
    return _slugify(fact), fact


def register(mcp):

    @mcp.tool()
    async def remember_this(fact: str) -> str:
        """
        Store a fact or piece of information for future recall.

        Args:
            fact: The information to remember (e.g. "My standup is at 10am every weekday").
        """
        from orion.services.memory import memory_service

        key, value = await _extract_key_value(fact)
        memory_service.remember(key=key, value=value, source="voice")
        return f"Noted, sir. I'll remember that {key} is {value}."

    @mcp.tool()
    async def what_do_i_know_about(topic: str) -> str:
        """
        Recall stored information about a topic.

        Args:
            topic: The topic to search memory for (e.g. "standup time", "Priya's email").
        """
        from orion.services.memory import memory_service

        results = memory_service.recall(topic)
        if not results:
            return f"I don't have anything stored about '{topic}', sir."

        if len(results) == 1:
            return f"{results[0].key}: {results[0].value}"

        lines = [f"Here's what I know about '{topic}':"]
        for mem in results:
            lines.append(f"  • {mem.key}: {mem.value}")
        return "\n".join(lines)

    @mcp.tool()
    async def forget(topic: str) -> str:
        """
        Remove stored information about a topic from memory.

        Args:
            topic: The topic to forget.
        """
        from orion.services.memory import memory_service

        found = memory_service.forget(topic)
        if found:
            return f"Done, sir. I've forgotten about '{topic}'."
        return f"I didn't have anything stored about '{topic}', sir."
