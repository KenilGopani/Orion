"""
Ask an LLM which tool it would call — the same decision the voice LLM makes.

Conversations are written in one neutral form and converted per transport:
OpenAI-compatible chat completions (Gemini, OpenAI, Groq, Ollama) or the
Anthropic Messages API (Claude). That keeps the eval provider-neutral, like
``orion.llm.complete_text``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx

from orion.llm.providers import ProviderSpec, Transport


@dataclass
class ToolSpec:
    """A tool as the voice LLM sees it (from the generated MCP surface)."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class Turn:
    """One conversation turn in transport-neutral form.

    ``role`` is "user" or "tool". A "tool" turn records that the assistant
    called ``tool_name`` and got ``content`` back, as when the voice LLM reads
    an email whose body is untrusted.
    """

    role: str
    content: str
    tool_name: str = ""
    tool_args: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]


def openai_messages(system: str, turns: list[Turn]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for i, turn in enumerate(turns):
        if turn.role == "tool":
            call_id = f"call_{i}"
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": call_id,
                    "type": "function",
                    "function": {"name": turn.tool_name, "arguments": json.dumps(turn.tool_args)},
                }],
            })
            messages.append({"role": "tool", "tool_call_id": call_id, "content": turn.content})
        else:
            messages.append({"role": "user", "content": turn.content})
    return messages


def anthropic_messages(turns: list[Turn]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for i, turn in enumerate(turns):
        if turn.role == "tool":
            call_id = f"toolu_{i}"
            messages.append({
                "role": "assistant",
                "content": [{"type": "tool_use", "id": call_id, "name": turn.tool_name, "input": turn.tool_args}],
            })
            messages.append({
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": call_id, "content": turn.content}],
            })
        else:
            messages.append({"role": "user", "content": turn.content})
    return messages


async def choose_tools(
    spec: ProviderSpec,
    system: str,
    turns: list[Turn],
    tools: list[ToolSpec],
    *,
    timeout: float = 60,
) -> list[ToolCall]:
    """The tool calls ``spec``'s voice model makes for this conversation."""
    if spec.transport is Transport.ANTHROPIC:
        return await _anthropic(spec, system, turns, tools, timeout)
    return await _openai_compat(spec, system, turns, tools, timeout)


async def _openai_compat(
    spec: ProviderSpec, system: str, turns: list[Turn], tools: list[ToolSpec], timeout: float
) -> list[ToolCall]:
    payload: dict[str, Any] = {
        "model": spec.model,
        "messages": openai_messages(system, turns),
        "tools": [
            {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
            for t in tools
        ],
        "tool_choice": "auto",
    }
    if spec.supports_temperature:
        payload["temperature"] = 0
    headers = {"Authorization": f"Bearer {spec.api_key()}"} if spec.api_key() else {}
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(f"{(spec.base_url or '').rstrip('/')}/chat/completions", json=payload, headers=headers)
        resp.raise_for_status()
        message = resp.json()["choices"][0]["message"]
    calls = []
    for call in message.get("tool_calls") or []:
        raw = call["function"].get("arguments") or "{}"
        try:
            arguments = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            arguments = {"_unparsed": raw}
        calls.append(ToolCall(call["function"]["name"], arguments or {}))
    return calls


async def _anthropic(
    spec: ProviderSpec, system: str, turns: list[Turn], tools: list[ToolSpec], timeout: float
) -> list[ToolCall]:
    from anthropic import AsyncAnthropic
    from anthropic.types import ToolUseBlock

    client = AsyncAnthropic(api_key=spec.api_key(), timeout=timeout)
    message = await client.messages.create(
        model=spec.model,
        max_tokens=1024,
        system=system,
        messages=anthropic_messages(turns),  # type: ignore[arg-type]
        tools=[{"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools],  # type: ignore[misc]
    )
    return [
        ToolCall(block.name, dict(block.input) if isinstance(block.input, dict) else {})
        for block in message.content
        if isinstance(block, ToolUseBlock)
    ]
