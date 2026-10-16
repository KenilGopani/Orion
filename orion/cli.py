"""
``orion`` command-line entry point.

    orion up              API + MCP tools + scheduler + dashboard, plus the voice agent
    orion up --no-voice   everything except the voice agent
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys

import uvicorn

from orion.config import config

logger = logging.getLogger("orion.cli")

_VOICE_STOP_TIMEOUT = 10  # seconds to wait for the voice agent to exit cleanly


def _voice_unavailable_reason() -> str | None:
    """Why the voice agent can't start, or ``None`` if it can."""
    missing = [
        name
        for name, value in (
            ("LIVEKIT_URL", config.livekit_url),
            ("LIVEKIT_API_KEY", config.livekit_api_key),
            ("LIVEKIT_API_SECRET", config.livekit_api_secret),
        )
        if not value
    ]
    if missing:
        return f"missing {', '.join(missing)}"
    return None


def _start_voice(port: int) -> subprocess.Popen[bytes] | None:
    """Start the LiveKit voice agent as a child process, if it can run."""
    reason = _voice_unavailable_reason()
    if reason:
        logger.warning("Voice agent not started (%s). Running without voice.", reason)
        return None
    logger.info("Starting voice agent…")
    # LiveKit's worker model needs its own process; it reaches the tools over /mcp/sse.
    env = {**os.environ, "ORION_PORT": str(port)}
    return subprocess.Popen([sys.executable, "-m", "agent", "dev"], env=env)


def _stop_voice(proc: subprocess.Popen[bytes] | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=_VOICE_STOP_TIMEOUT)
    except subprocess.TimeoutExpired:
        logger.warning("Voice agent did not stop in %ss; killing it.", _VOICE_STOP_TIMEOUT)
        proc.kill()


def _up(args: argparse.Namespace) -> int:
    from orion.app import create_app

    config.validate()
    voice = None if args.no_voice or not config.enable_voice else _start_voice(args.port)
    try:
        logger.info("Orion on http://%s:%d  (dashboard /, API /api, MCP /mcp/sse)", args.host, args.port)
        uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")
    finally:
        _stop_voice(voice)
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(name)-20s  %(levelname)-7s  %(message)s",
    )
    parser = argparse.ArgumentParser(prog="orion", description="Orion voice agent")
    commands = parser.add_subparsers(dest="command", required=True)

    up = commands.add_parser("up", help="run Orion (API, tools, scheduler, dashboard, voice)")
    up.add_argument("--host", default="127.0.0.1", help="interface to bind (default: 127.0.0.1)")
    up.add_argument("--port", type=int, default=config.port, help="port (default: ORION_PORT or 8000)")
    up.add_argument("--no-voice", action="store_true", help="don't start the voice agent")
    up.set_defaults(handler=_up)

    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    sys.exit(main())
