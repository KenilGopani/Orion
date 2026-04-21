"""
Configuration — load environment variables and expose typed config.
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    """Centralised configuration loaded from environment variables."""

    # Server identity
    server_name: str = field(default_factory=lambda: os.getenv("SERVER_NAME", "ORION"))

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


config = Config()
