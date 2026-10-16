"""
Orion — Voice Agent
============================
LiveKit Agents-powered voice assistant with MCP tool integration.

Connects: Microphone → VAD → STT → LLM (+ MCP Tools) → TTS → Speaker

The agent uses the Orion persona and connects to the Orion app's MCP
endpoint (/mcp/sse) for tool execution. All tools delegate to the
OpenClaw daemon for real-world actions.

Run:
    uv run orion up          # started automatically alongside the app
    uv run orion_voice       # or on its own, against a running app
"""

from __future__ import annotations

import asyncio
import sys
import logging

from dotenv import load_dotenv
from livekit.agents import JobContext, WorkerOptions, cli
from livekit.agents.voice import Agent, AgentSession
from livekit.agents.llm import mcp

# Plugins
from livekit.plugins import (
    google as lk_google,
    openai as lk_openai,
    sarvam,
    silero,
    elevenlabs,
)

from orion.persona import get_system_prompt
from orion.config import config
from orion.llm import resolve
from orion.voice_outcomes import OutcomeAnnouncer

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

load_dotenv()

STT_PROVIDER = config.stt_provider
LLM_PROVIDER = config.llm_provider
TTS_PROVIDER = config.tts_provider

OPENAI_TTS_MODEL = "tts-1"
OPENAI_TTS_VOICE = "onyx"  # Deep, composed male voice
TTS_SPEED = 1.10

SARVAM_TTS_LANGUAGE = "en-IN"
SARVAM_TTS_SPEAKER = "rahul"

ORION_PORT = config.port

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-20s  %(levelname)-7s  %(message)s",
)
logger = logging.getLogger("orion.agent")


# ---------------------------------------------------------------------------
# MCP Server URL
# ---------------------------------------------------------------------------

def _mcp_server_url() -> str:
    url = f"http://127.0.0.1:{ORION_PORT}/mcp/sse"
    logger.info("MCP Server URL: %s", url)
    return url


# ---------------------------------------------------------------------------
# Build provider instances
# ---------------------------------------------------------------------------

def _build_stt():
    if STT_PROVIDER == "whisper_local":
        logger.info(
            "STT → local Whisper (%s @ %s)",
            config.whisper_local_model,
            config.whisper_local_url,
        )
        # Any OpenAI-compatible local Whisper server (whisper.cpp, faster-whisper-server).
        # Non-streaming: LiveKit segments audio with VAD and calls recognize() per turn.
        return lk_openai.STT(
            model=config.whisper_local_model,
            base_url=config.whisper_local_url,
            api_key="local",  # ignored by local servers, but the client requires a value
        )
    elif STT_PROVIDER == "parakeet_local":
        logger.info(
            "STT → local Parakeet (%s @ %s)",
            config.parakeet_model,
            config.parakeet_local_url,
        )
        # `orion parakeet-server` speaks the OpenAI transcription API. Like
        # Whisper it's non-streaming: LiveKit segments audio with VAD per turn.
        return lk_openai.STT(
            model=config.parakeet_model,
            base_url=config.parakeet_local_url,
            api_key="local",  # ignored by the local server, but the client requires a value
        )
    elif STT_PROVIDER == "sarvam":
        logger.info("STT → Sarvam Saaras v3")
        return sarvam.STT(
            language="unknown",
            model="saaras:v3",
            mode="transcribe",
            flush_signal=True,
            sample_rate=16000,
        )
    elif STT_PROVIDER == "whisper":
        logger.info("STT → OpenAI Whisper")
        return lk_openai.STT(model="whisper-1")
    elif STT_PROVIDER == "groq":
        logger.info("STT → Groq Whisper")
        return lk_openai.STT(
            model="whisper-large-v3",
            base_url="https://api.groq.com/openai/v1",
            api_key=config.groq_api_key,
        )
    elif STT_PROVIDER == "deepgram":
        logger.info("STT → Deepgram")
        from livekit.plugins import deepgram
        return deepgram.STT()
    else:
        raise ValueError(f"Unknown STT_PROVIDER: {STT_PROVIDER!r}")


def _build_llm():
    """Build the voice-pipeline LLM from the shared provider registry.

    Each provider declares which LiveKit plugin serves it, so adding a
    provider means editing ``orion/llm/providers.py`` — not this function.
    """
    spec = resolve(LLM_PROVIDER)
    logger.info("LLM → %s (%s)", spec.name, spec.model)

    if spec.livekit_plugin == "google":
        return lk_google.LLM(model=spec.model, api_key=spec.api_key())

    if spec.livekit_plugin == "anthropic":
        # Native Anthropic plugin — not an OpenAI-compatibility shim.
        try:
            from livekit.plugins import anthropic as lk_anthropic
        except ImportError as exc:
            raise RuntimeError(
                "LLM_PROVIDER=claude requires the Anthropic plugin. "
                "Install it with: uv add livekit-plugins-anthropic"
            ) from exc
        return lk_anthropic.LLM(model=spec.model, api_key=spec.api_key())

    # Everything else is OpenAI-compatible — same plugin, different base_url.
    kwargs: dict = {"model": spec.model}
    if spec.base_url:
        kwargs["base_url"] = spec.base_url
    # Local servers ignore the key but the client requires a non-empty value.
    kwargs["api_key"] = spec.api_key() or "local"
    return lk_openai.LLM(**kwargs)


def _build_tts():
    if TTS_PROVIDER == "kokoro":
        logger.info(
            "TTS → local Kokoro (%s @ %s)",
            config.kokoro_voice,
            config.kokoro_url,
        )
        # Kokoro via an OpenAI-compatible server (e.g. kokoro-fastapi).
        # Non-streaming, but LiveKit auto-wraps it in a tts.StreamAdapter with a
        # sentence tokenizer, so playback starts after the first sentence.
        return lk_openai.TTS(
            model="kokoro",
            voice=config.kokoro_voice,
            base_url=config.kokoro_url,
            api_key="local",  # ignored by local servers, but the client requires a value
            speed=TTS_SPEED,
        )
    elif TTS_PROVIDER == "mlx_audio":
        logger.info(
            "TTS → mlx-audio (%s, %s @ %s)",
            config.mlx_audio_model,
            config.mlx_audio_voice,
            config.mlx_audio_url,
        )
        # mlx-audio's OpenAI-compatible server. WAV, because mlx-audio needs
        # ffmpeg for compressed formats and the plugin's default is MP3.
        return lk_openai.TTS(
            model=config.mlx_audio_model,
            voice=config.mlx_audio_voice,
            base_url=config.mlx_audio_url,
            api_key="local",  # ignored by the local server, but the client requires a value
            response_format="wav",
            speed=TTS_SPEED,
        )
    elif TTS_PROVIDER == "sarvam":
        logger.info("TTS → Sarvam Bulbul v3")
        return sarvam.TTS(
            target_language_code=SARVAM_TTS_LANGUAGE,
            model="bulbul:v3",
            speaker=SARVAM_TTS_SPEAKER,
            pace=TTS_SPEED,
        )
    elif TTS_PROVIDER == "openai":
        logger.info("TTS → OpenAI TTS (%s / %s)", OPENAI_TTS_MODEL, OPENAI_TTS_VOICE)
        return lk_openai.TTS(
            model=OPENAI_TTS_MODEL,
            voice=OPENAI_TTS_VOICE,
            speed=TTS_SPEED,
        )
    elif TTS_PROVIDER == "elevenlabs":
        logger.info("TTS → ElevenLabs")
        return elevenlabs.TTS(
            model="eleven_turbo_v2_5",
            voice_id=config.elevenlabs_voice_id,
        )
    else:
        raise ValueError(f"Unknown TTS_PROVIDER: {TTS_PROVIDER!r}")


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class OrionAgent(Agent):
    """
    Orion — Voice agent powered by LiveKit.

    All tools are provided via the MCP server, which delegates to OpenClaw.
    """

    def __init__(self, stt, llm, tts) -> None:
        super().__init__(
            instructions=get_system_prompt(),
            stt=stt,
            llm=llm,
            tts=tts,
            vad=silero.VAD.load(),
            mcp_servers=[
                mcp.MCPServerHTTP(
                    url=_mcp_server_url(),
                    transport_type="sse",
                    client_session_timeout_seconds=30,
                ),
            ],
        )

    async def on_enter(self) -> None:
        """Greet the user based on the current time of day."""
        from datetime import datetime

        hour = datetime.now().hour  # Local time

        name = config.user_name

        if hour >= 22 or hour < 5:
            greeting = (
                f"Greet the user: 'Good evening, {name}. Burning the midnight oil, I see. "
                f"All systems are online. How can I assist you?'"
            )
        elif 5 <= hour < 12:
            greeting = (
                f"Greet the user: 'Good morning, {name}. All systems are online. "
                f"What shall we tackle today?'"
            )
        elif 12 <= hour < 17:
            greeting = (
                f"Greet the user: 'Good afternoon, {name}. "
                f"How can I be of service?'"
            )
        else:  # 17–21
            greeting = (
                f"Greet the user: 'Good evening, {name}. "
                f"Ready when you are.'"
            )

        await self.session.generate_reply(instructions=greeting)


# ---------------------------------------------------------------------------
# LiveKit entry point
# ---------------------------------------------------------------------------

def _turn_detection() -> str:
    return "stt" if STT_PROVIDER == "sarvam" else "vad"


def _endpointing_delay() -> float:
    return {
        "sarvam": 0.07,
        "whisper": 0.3,
        "whisper_local": 0.3,
        "parakeet_local": 0.2,
        "groq": 0.3,
        "deepgram": 0.2,
    }.get(STT_PROVIDER, 0.1)


async def entrypoint(ctx: JobContext) -> None:
    logger.info(
        "Orion online — room: %s | STT=%s | LLM=%s | TTS=%s",
        ctx.room.name,
        STT_PROVIDER,
        LLM_PROVIDER,
        TTS_PROVIDER,
    )

    stt = _build_stt()
    llm = _build_llm()
    tts = _build_tts()

    session = AgentSession(
        turn_detection=_turn_detection(),
        min_endpointing_delay=_endpointing_delay(),
    )

    # ── Conversation logging ──────────────────────────────────────
    try:
        from orion.services.conversation import ConversationLogger

        conv_logger = ConversationLogger(session_id=ctx.room.name)

        @session.on("user_input_transcribed")
        def _on_user_input(event):
            if hasattr(event, "text") and event.text:
                conv_logger.log("user", event.text)
                logger.debug("Logged user: %s", event.text[:60])

        @session.on("agent_speech_committed")
        def _on_agent_speech(event):
            if hasattr(event, "content") and event.content:
                conv_logger.log("assistant", event.content)
                logger.debug("Logged assistant: %s", event.content[:60])

        logger.info("Conversation logging enabled for session: %s", ctx.room.name)
    except Exception as exc:
        logger.warning("Conversation logging not available: %s", exc)

    await session.start(
        agent=OrionAgent(stt=stt, llm=llm, tts=tts),
        room=ctx.room,
    )

    # ── Approval outcomes ─────────────────────────────────────────
    # A turn ends at "waiting for your approval"; when the user later approves
    # or rejects in the dashboard, say what happened at the next pause.
    announcer = OutcomeAnnouncer(
        url=f"http://127.0.0.1:{ORION_PORT}/api/events/outcomes",
        speak=lambda text: session.say(text),
        is_busy=lambda: session.user_state == "speaking"
        or session.agent_state in ("speaking", "thinking"),
    )
    outcomes = asyncio.create_task(announcer.run())

    async def _stop_outcomes() -> None:
        outcomes.cancel()

    ctx.add_shutdown_callback(_stop_outcomes)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    config.validate(require_voice=True)
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))


def dev():
    """Wrapper to run the agent in dev mode automatically."""
    if len(sys.argv) == 1:
        sys.argv.append("dev")
    main()


if __name__ == "__main__":
    main()
