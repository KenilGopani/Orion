"""
Single source of truth for LLM providers.

Every place in Orion that needs an LLM — the voice agent, the task planner,
and memory key extraction — resolves its provider from this one table.
Adding a provider means adding one ``ProviderSpec`` here.

Two transports are supported:

``OPENAI_COMPAT``
    Gemini, OpenAI, Groq and Ollama all expose an OpenAI-compatible
    ``/chat/completions`` endpoint, so they share a single HTTP path and a
    single LiveKit plugin (``livekit.plugins.openai``) with a different
    ``base_url``.

``ANTHROPIC``
    Claude uses the official ``anthropic`` SDK and the native LiveKit
    Anthropic plugin. We deliberately do *not* route Claude through an
    OpenAI-compatibility shim — the native Messages API is the supported
    path and handles tool use correctly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum


class Transport(str, Enum):
    """How Orion talks to a provider."""

    OPENAI_COMPAT = "openai_compat"
    ANTHROPIC = "anthropic"


@dataclass(frozen=True)
class ProviderSpec:
    """Everything Orion needs to know about one LLM provider."""

    name: str
    transport: Transport

    #: Model used by the conversational voice agent.
    model: str

    #: Model used for utility calls (planning, memory extraction). Falls back
    #: to :attr:`model` when unset — cheaper/faster models often suffice here.
    utility_model: str | None = None

    #: Base URL for OPENAI_COMPAT providers. Unused by the Anthropic transport.
    base_url: str | None = None

    #: Environment variable holding the API key. ``None`` means the provider
    #: needs no credentials (i.e. it runs locally and is free).
    api_key_env: str | None = None

    #: Which LiveKit plugin builds the voice-pipeline LLM.
    livekit_plugin: str = "openai"

    #: Anthropic models reject the ``temperature`` parameter and return 400,
    #: so the neutral client omits it for providers that opt out.
    supports_temperature: bool = True

    #: True when the provider runs on this machine at no cost.
    is_local: bool = False

    @property
    def requires_key(self) -> bool:
        return self.api_key_env is not None

    @property
    def utility(self) -> str:
        """Model to use for planning / extraction calls."""
        return self.utility_model or self.model

    def api_key(self) -> str:
        """Read this provider's key from the environment (empty when local)."""
        if not self.api_key_env:
            return ""
        return os.getenv(self.api_key_env, "")


# ── The registry ──────────────────────────────────────────────────────────────

PROVIDERS: dict[str, ProviderSpec] = {
    "gemini": ProviderSpec(
        name="gemini",
        transport=Transport.OPENAI_COMPAT,
        model="gemini-2.5-flash",
        utility_model="gemini-2.0-flash",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        api_key_env="GOOGLE_API_KEY",
        livekit_plugin="google",
    ),
    "openai": ProviderSpec(
        name="openai",
        transport=Transport.OPENAI_COMPAT,
        model="gpt-4o",
        utility_model="gpt-4o-mini",
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        livekit_plugin="openai",
    ),
    "claude": ProviderSpec(
        name="claude",
        transport=Transport.ANTHROPIC,
        # Sonnet 5 is the latency/quality sweet spot for a voice turn.
        # Set ORION_LLM_MODEL=claude-opus-5 for maximum capability.
        model="claude-sonnet-5",
        api_key_env="ANTHROPIC_API_KEY",
        livekit_plugin="anthropic",
        supports_temperature=False,
    ),
    "groq": ProviderSpec(
        name="groq",
        transport=Transport.OPENAI_COMPAT,
        model="llama-3.3-70b-versatile",
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
        livekit_plugin="openai",
    ),
    "ollama": ProviderSpec(
        name="ollama",
        transport=Transport.OPENAI_COMPAT,
        # Free and fully local. qwen3.5:4b (3.3 GB, tool calling) leaves room for
        # local STT/TTS and OpenClaw on a 16 GB Mac; with 24 GB+ prefer
        # ORION_LLM_MODEL=qwen3.5:9b. Pull with: ollama pull qwen3.5:4b
        model="qwen3.5:4b",
        base_url=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/v1"),
        api_key_env=None,
        livekit_plugin="openai",
        is_local=True,
    ),
}

#: Accepted aliases so users can write what they naturally say.
ALIASES: dict[str, str] = {
    "chatgpt": "openai",
    "gpt": "openai",
    "anthropic": "claude",
    "google": "gemini",
    "local": "ollama",
}


def resolve(provider: str) -> ProviderSpec:
    """Look up a provider by name or alias.

    Raises:
        ValueError: with the list of valid names, if the provider is unknown.
    """
    key = (provider or "").strip().lower()
    key = ALIASES.get(key, key)

    spec = PROVIDERS.get(key)
    if spec is None:
        valid = ", ".join(sorted(PROVIDERS)) + " (aliases: " + ", ".join(sorted(ALIASES)) + ")"
        raise ValueError(f"Unknown LLM provider {provider!r}. Valid options: {valid}")

    # Allow a single env override of the model without editing this table.
    override = os.getenv("ORION_LLM_MODEL", "").strip()
    if override:
        from dataclasses import replace

        return replace(spec, model=override, utility_model=override)

    return spec
