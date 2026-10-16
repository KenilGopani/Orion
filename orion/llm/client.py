"""
Provider-neutral text completion used by the planner and memory extraction.

Callers pass a system prompt and a user message and get back raw text. The
transport differences (OpenAI-compatible JSON vs the Anthropic Messages API)
are handled here so no caller has to branch on provider.
"""

from __future__ import annotations

import logging

import httpx

from orion.llm.providers import ProviderSpec, Transport, resolve

logger = logging.getLogger("orion.llm")

DEFAULT_MAX_TOKENS = 2048
DEFAULT_TIMEOUT = 30


class LLMUnavailable(RuntimeError):
    """Raised when a provider cannot be reached or has no credentials.

    Callers are expected to catch this and degrade gracefully rather than
    propagate it — Orion should never crash because an LLM was unreachable.
    """


async def complete_text(
    *,
    system: str,
    user: str,
    provider: str | ProviderSpec,
    temperature: float = 0.1,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Return the model's raw text response.

    Raises:
        LLMUnavailable: when the provider has no key, is unknown, or errors.
    """
    spec = provider if isinstance(provider, ProviderSpec) else resolve(provider)

    if spec.requires_key and not spec.api_key():
        raise LLMUnavailable(
            f"Provider '{spec.name}' needs {spec.api_key_env}, which is not set"
        )

    try:
        if spec.transport is Transport.ANTHROPIC:
            return await _complete_anthropic(spec, system, user, max_tokens, timeout)
        return await _complete_openai_compat(
            spec, system, user, temperature, max_tokens, timeout
        )
    except LLMUnavailable:
        raise
    except Exception as exc:
        raise LLMUnavailable(f"{spec.name} request failed: {exc}") from exc


# ── Transports ────────────────────────────────────────────────────────────────

async def _complete_openai_compat(
    spec: ProviderSpec,
    system: str,
    user: str,
    temperature: float,
    max_tokens: int,
    timeout: int,
) -> str:
    """Gemini / OpenAI / Groq / Ollama — one shared OpenAI-compatible path."""
    payload: dict = {
        "model": spec.utility,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
    }
    if spec.supports_temperature:
        payload["temperature"] = temperature

    headers = {"Content-Type": "application/json"}
    key = spec.api_key()
    if key:
        headers["Authorization"] = f"Bearer {key}"

    url = f"{(spec.base_url or '').rstrip('/')}/chat/completions"

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    return data.get("choices", [{}])[0].get("message", {}).get("content", "") or ""


async def _complete_anthropic(
    spec: ProviderSpec,
    system: str,
    user: str,
    max_tokens: int,
    timeout: int,
) -> str:
    """Claude via the official Anthropic SDK.

    Note: Anthropic models reject ``temperature``, so it is never sent. The
    system prompt is a top-level parameter rather than a message role.
    """
    try:
        from anthropic import AsyncAnthropic
        from anthropic.types import TextBlock
    except ImportError as exc:  # pragma: no cover - depends on optional install
        raise LLMUnavailable(
            "The 'anthropic' package is required for the claude provider. "
            "Install it with: uv add anthropic"
        ) from exc

    client = AsyncAnthropic(api_key=spec.api_key(), timeout=timeout)
    message = await client.messages.create(
        model=spec.utility,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )

    # Concatenate any text blocks, ignoring thinking/tool-use blocks.
    return "".join(
        block.text for block in message.content if isinstance(block, TextBlock)
    )
