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
from typing import Any

from pydantic import BaseModel, Field

from orion.core.models import ToolSafetyLevel
from orion.core.registry import ToolDefinition
from orion.tools._safe import Line

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

    # Try LLM extraction — provider-neutral, works with any configured backend
    try:
        import json

        from orion.llm import complete_text

        raw = await complete_text(
            system=(
                'Extract a short key and value from this fact. '
                'Return ONLY JSON: {"key": "...", "value": "..."}\n'
                'Example: "My standup is at 10am on weekdays" → '
                '{"key": "standup", "value": "10am on weekdays"}'
            ),
            user=fact,
            provider=config.llm_provider,
            temperature=0.0,
            max_tokens=256,
            timeout=10,
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



class RememberInput(BaseModel):
    fact: Line = Field(description='The information to remember, e.g. "My standup is at 10am every weekday".')


class RecallInput(BaseModel):
    topic: Line = Field(description='The topic to search memory for, e.g. "standup time".')


class ForgetInput(BaseModel):
    topic: Line = Field(description="The topic to forget.")


async def _remember(payload: RememberInput) -> dict[str, str]:
    from orion.services.memory import memory_service

    key, value = await _extract_key_value(payload.fact)
    memory_service.remember(key=key, value=value, source="voice")
    return {"message": f"Noted, sir. I'll remember that {key} is {value}."}


def _recall(payload: RecallInput) -> dict[str, str]:
    from orion.services.memory import memory_service

    results = memory_service.recall(payload.topic)
    if not results:
        return {"message": f"I don't have anything stored about '{payload.topic}', sir."}
    if len(results) == 1:
        return {"message": f"{results[0].key}: {results[0].value}"}
    lines = [f"Here's what I know about '{payload.topic}':"]
    lines += [f"  • {mem.key}: {mem.value}" for mem in results]
    return {"message": "\n".join(lines)}


def _forget(payload: ForgetInput) -> dict[str, str]:
    from orion.services.memory import memory_service

    if memory_service.forget(payload.topic):
        return {"message": f"Done, sir. I've forgotten about '{payload.topic}'."}
    return {"message": f"I didn't have anything stored about '{payload.topic}', sir."}


TOOLS: list[ToolDefinition[Any]] = [
    ToolDefinition(
        name="remember_this",
        description="Store a fact or piece of information for future recall.",
        input_model=RememberInput,
        handler=_remember,
        safety_level=ToolSafetyLevel.LOW_RISK,
        action="Saving that memory",
    ),
    ToolDefinition(
        name="what_do_i_know_about",
        description="Recall stored information about a topic.",
        input_model=RecallInput,
        handler=_recall,
        safety_level=ToolSafetyLevel.READ_ONLY,
        action="The memory lookup",
    ),
    ToolDefinition(
        name="forget",
        description="Remove stored information about a topic from memory.",
        input_model=ForgetInput,
        handler=_forget,
        safety_level=ToolSafetyLevel.LOW_RISK,
        action="Forgetting that",
    ),
]
