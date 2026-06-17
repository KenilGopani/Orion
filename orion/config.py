"""
Configuration — load environment variables and expose typed config.
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


def _env_bool(key: str, default: str = "false") -> bool:
    """Parse a boolean environment variable."""
    return os.getenv(key, default).lower() in {"true", "1", "yes"}


@dataclass
class Config:
    """Centralised configuration loaded from environment variables."""

    # Server identity
    server_name: str = field(default_factory=lambda: os.getenv("SERVER_NAME", "ORION"))

    # ── Development mode ──────────────────────────────────────────
    dev_mode: bool = field(default_factory=lambda: _env_bool("DEV_MODE"))
    mock_openclaw: bool = field(default_factory=lambda: _env_bool("MOCK_OPENCLAW"))

    # ── Per-subsystem feature flags ───────────────────────────────
    enable_voice: bool = field(default_factory=lambda: _env_bool("ENABLE_VOICE", "true"))
    enable_scheduler: bool = field(default_factory=lambda: _env_bool("ENABLE_SCHEDULER"))
    enable_api: bool = field(default_factory=lambda: _env_bool("ENABLE_API", "true"))

    # ── Scheduled Actions ─────────────────────────────────────────
    morning_briefing_enabled: bool = field(
        default_factory=lambda: os.getenv("MORNING_BRIEFING", "false").lower() == "true"
    )
    morning_briefing_time: str = field(
        default_factory=lambda: os.getenv("MORNING_BRIEFING_TIME", "08:00")
    )
    email_digest_enabled: bool = field(
        default_factory=lambda: os.getenv("EMAIL_DIGEST", "false").lower() == "true"
    )
    email_digest_time: str = field(
        default_factory=lambda: os.getenv("EMAIL_DIGEST_TIME", "09:00")
    )

    # ── Provider switches ─────────────────────────────────────────
    stt_provider: str = field(default_factory=lambda: os.getenv("STT_PROVIDER", "groq"))
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "gemini"))
    tts_provider: str = field(default_factory=lambda: os.getenv("TTS_PROVIDER", "elevenlabs"))

    # ── API keys ──────────────────────────────────────────────────
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    google_api_key: str = field(default_factory=lambda: os.getenv("GOOGLE_API_KEY", ""))
    groq_api_key: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    elevenlabs_api_key: str = field(default_factory=lambda: os.getenv("ELEVEN_API_KEY", ""))
    elevenlabs_voice_id: str = field(
        default_factory=lambda: os.getenv("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")
    )
    sarvam_api_key: str = field(default_factory=lambda: os.getenv("SARVAM_API_KEY", ""))
    deepgram_api_key: str = field(default_factory=lambda: os.getenv("DEEPGRAM_API_KEY", ""))

    # ── LiveKit ───────────────────────────────────────────────────
    livekit_url: str = field(default_factory=lambda: os.getenv("LIVEKIT_URL", ""))
    livekit_api_key: str = field(default_factory=lambda: os.getenv("LIVEKIT_API_KEY", ""))
    livekit_api_secret: str = field(default_factory=lambda: os.getenv("LIVEKIT_API_SECRET", ""))

    # ── OpenClaw ──────────────────────────────────────────────────
    openclaw_url: str = field(
        default_factory=lambda: os.getenv("OPENCLAW_API_URL", "http://127.0.0.1:18789")
    )
    openclaw_token: str = field(
        default_factory=lambda: os.getenv("OPENCLAW_GATEWAY_TOKEN", "")
    )

    # ── Persona ───────────────────────────────────────────────────
    user_name: str = field(default_factory=lambda: os.getenv("ORION_USER_NAME", "sir"))
    wake_word: str = field(default_factory=lambda: os.getenv("ORION_WAKE_WORD", "orion"))

    # ── MCP server ────────────────────────────────────────────────
    mcp_server_port: int = field(
        default_factory=lambda: int(os.getenv("MCP_SERVER_PORT", "8000"))
    )

    # ── Validation ────────────────────────────────────────────────

    # Provider → (config field, env var name) required keys
    _STT_KEYS: dict[str, tuple[str, str]] = field(default_factory=lambda: {
        "groq": ("groq_api_key", "GROQ_API_KEY"),
        "whisper": ("openai_api_key", "OPENAI_API_KEY"),
        "openai": ("openai_api_key", "OPENAI_API_KEY"),
        "sarvam": ("sarvam_api_key", "SARVAM_API_KEY"),
        "deepgram": ("deepgram_api_key", "DEEPGRAM_API_KEY"),
    }, repr=False)

    _LLM_KEYS: dict[str, tuple[str, str]] = field(default_factory=lambda: {
        "gemini": ("google_api_key", "GOOGLE_API_KEY"),
        "openai": ("openai_api_key", "OPENAI_API_KEY"),
        "groq": ("groq_api_key", "GROQ_API_KEY"),
    }, repr=False)

    _TTS_KEYS: dict[str, tuple[str, str]] = field(default_factory=lambda: {
        "elevenlabs": ("elevenlabs_api_key", "ELEVEN_API_KEY"),
        "openai": ("openai_api_key", "OPENAI_API_KEY"),
        "sarvam": ("sarvam_api_key", "SARVAM_API_KEY"),
    }, repr=False)

    def validate(self, require_voice: bool = False) -> None:
        """Validate configuration, raising SystemExit with helpful message on failure.

        Args:
            require_voice: If True, also validate LiveKit and provider keys.
                           Set to True when starting the voice agent.
        """
        if self.dev_mode:
            return  # skip validation entirely in dev mode

        errors: list[str] = []

        if require_voice:
            # LiveKit keys are required for the voice agent
            if not self.livekit_url:
                errors.append("  Missing: LIVEKIT_URL")
            if not self.livekit_api_key:
                errors.append("  Missing: LIVEKIT_API_KEY")
            if not self.livekit_api_secret:
                errors.append("  Missing: LIVEKIT_API_SECRET")

            # Check that the selected STT provider has its API key set
            stt_req = self._STT_KEYS.get(self.stt_provider)
            if stt_req:
                attr, env = stt_req
                if not getattr(self, attr):
                    errors.append(f"  Missing: {env} (required for STT provider '{self.stt_provider}')")

            # Check that the selected LLM provider has its API key set
            llm_req = self._LLM_KEYS.get(self.llm_provider)
            if llm_req:
                attr, env = llm_req
                if not getattr(self, attr):
                    errors.append(f"  Missing: {env} (required for LLM provider '{self.llm_provider}')")

            # Check that the selected TTS provider has its API key set
            tts_req = self._TTS_KEYS.get(self.tts_provider)
            if tts_req:
                attr, env = tts_req
                if not getattr(self, attr):
                    errors.append(f"  Missing: {env} (required for TTS provider '{self.tts_provider}')")

        if errors:
            raise SystemExit(
                "\n[Orion] Cannot start — missing required environment variables:\n\n"
                + "\n".join(errors)
                + "\n\nCopy .env.example to .env and fill in the values."
                + "\nFor development without API keys: make dev\n"
            )


config = Config()
