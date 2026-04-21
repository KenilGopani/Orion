"""
Orion — Voice Agent
============================
LiveKit Agents-powered voice assistant with MCP tool integration.

Connects: Microphone → VAD → STT → LLM (+ MCP Tools) → TTS → Speaker

The agent uses the Orion persona and connects to the FastMCP
server (server.py) for tool execution. All tools delegate to the
OpenClaw daemon for real-world actions.

Run:
    uv run orion_voice
"""

from __future__ import annotations

import os
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

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

load_dotenv()

STT_PROVIDER = config.stt_provider
LLM_PROVIDER = config.llm_provider
TTS_PROVIDER = config.tts_provider

GEMINI_LLM_MODEL = "gemini-2.5-flash"
OPENAI_LLM_MODEL = "gpt-4o"

OPENAI_TTS_MODEL = "tts-1"
OPENAI_TTS_VOICE = "onyx"  # Deep, composed male voice
TTS_SPEED = 1.10

SARVAM_TTS_LANGUAGE = "en-IN"
SARVAM_TTS_SPEAKER = "rahul"

MCP_SERVER_PORT = config.mcp_server_port

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
    url = f"http://127.0.0.1:{MCP_SERVER_PORT}/sse"
    logger.info("MCP Server URL: %s", url)
    return url


# ---------------------------------------------------------------------------
# Build provider instances
# ---------------------------------------------------------------------------

def _build_stt():
    if STT_PROVIDER == "sarvam":
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
    if LLM_PROVIDER == "openai":
        logger.info("LLM → OpenAI (%s)", OPENAI_LLM_MODEL)
        return lk_openai.LLM(model=OPENAI_LLM_MODEL)
    elif LLM_PROVIDER == "gemini":
        logger.info("LLM → Google Gemini (%s)", GEMINI_LLM_MODEL)
        return lk_google.LLM(
            model=GEMINI_LLM_MODEL,
            api_key=config.google_api_key,
        )
    elif LLM_PROVIDER == "groq":
        logger.info("LLM → Groq Llama 3.3 (llama-3.3-70b-versatile)")
        return lk_openai.LLM(
            model="llama-3.3-70b-versatile",
            base_url="https://api.groq.com/openai/v1",
            api_key=config.groq_api_key,
        )
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {LLM_PROVIDER!r}")


def _build_tts():
    if TTS_PROVIDER == "sarvam":
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
        from datetime import datetime, timezone

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
    return {"sarvam": 0.07, "whisper": 0.3, "groq": 0.3, "deepgram": 0.2}.get(
        STT_PROVIDER, 0.1
    )


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

    await session.start(
        agent=OrionAgent(stt=stt, llm=llm, tts=tts),
        room=ctx.room,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))


def dev():
    """Wrapper to run the agent in dev mode automatically."""
    if len(sys.argv) == 1:
        sys.argv.append("dev")
    main()


if __name__ == "__main__":
    main()
