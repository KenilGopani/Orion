"""
``orion`` command-line entry point.

    orion up              API + MCP tools + scheduler + dashboard, plus the voice agent
    orion up --no-voice   everything except the voice agent
    orion openclaw-config least-privilege OpenClaw agents + safety check
    orion parakeet-server local Parakeet speech-to-text (Apple Silicon)
    orion eval            tool-selection accuracy for the configured LLM
    orion bench           per-stage latency and memory on this machine
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

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


def _openclaw_config(args: argparse.Namespace) -> int:
    from orion.openclaw_setup import OPENCLAW_CONFIG_PATH, check_openclaw_config, config_snippet

    print(config_snippet())
    warnings = check_openclaw_config(config)
    if warnings:
        print(f"// Checks against {OPENCLAW_CONFIG_PATH}:", file=sys.stderr)
        for warning in warnings:
            print(f"//  ⚠ {warning}", file=sys.stderr)
    else:
        print(f"// {OPENCLAW_CONFIG_PATH} looks safe for Orion.", file=sys.stderr)
    return 0


def _parakeet_server(args: argparse.Namespace) -> int:
    from orion.speech.parakeet_server import create_parakeet_app, load_parakeet

    app = create_parakeet_app(load_parakeet(args.model), model_id=args.model)
    logger.info("Parakeet STT on http://%s:%d/v1 — set STT_PROVIDER=parakeet_local", args.host, args.port)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


def _eval(args: argparse.Namespace) -> int:
    import asyncio

    from orion.evals import voice_system_prompt, voice_tools
    from orion.evals.llm import choose_tools
    from orion.evals.tool_selection import CASES_PATH, load_cases, report, run_cases
    from orion.llm import resolve

    spec = resolve(args.provider)
    if spec.requires_key and not spec.api_key():
        print(f"{spec.api_key_env} is not set; it's required for provider {spec.name!r}.", file=sys.stderr)
        return 2
    cases = load_cases(args.cases or CASES_PATH)
    if args.limit:
        cases = cases[: args.limit]

    async def run() -> str:
        tools, safety = await voice_tools()
        system = voice_system_prompt()
        results = await run_cases(
            cases, lambda turns: choose_tools(spec, system, turns, tools), safety,
            concurrency=args.concurrency,
        )
        return report(spec.name, spec.model, results)

    print(f"Running {len(cases)} cases against {spec.name} / {spec.model}…", file=sys.stderr)
    text = asyncio.run(run())
    print(text)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    return 0


def _bench(args: argparse.Namespace) -> int:
    import asyncio

    from orion.evals.bench import bench_report, machine_info, run_bench

    stages = [s.strip() for s in args.stages.split(",") if s.strip()]
    audio = args.audio.read_bytes() if args.audio else None
    print(f"Benchmarking {', '.join(stages)} ({args.runs} runs each)…", file=sys.stderr)
    results = asyncio.run(run_bench(config, stages, max(args.runs, 1), audio))
    text = bench_report(results, machine_info(), args.runs)
    print(text)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
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

    oc = commands.add_parser(
        "openclaw-config",
        help="print least-privilege OpenClaw agent definitions and check the current config",
    )
    oc.set_defaults(handler=_openclaw_config)

    pk = commands.add_parser(
        "parakeet-server",
        help="run the local Parakeet speech-to-text server (Apple Silicon)",
    )
    pk.add_argument("--host", default="127.0.0.1", help="interface to bind (default: 127.0.0.1)")
    pk.add_argument("--port", type=int, default=8090, help="port (default: 8090)")
    pk.add_argument("--model", default=config.parakeet_model, help="Parakeet model id")
    pk.set_defaults(handler=_parakeet_server)

    ev = commands.add_parser("eval", help="tool-selection accuracy for the configured LLM provider")
    ev.add_argument("--provider", default=config.llm_provider, help="LLM provider (default: LLM_PROVIDER)")
    ev.add_argument("--cases", type=Path, default=None, help="cases file (default: evals/tool_selection.jsonl)")
    ev.add_argument("--limit", type=int, default=0, help="run only the first N cases")
    ev.add_argument("--concurrency", type=int, default=4, help="parallel requests (use 1 for local models)")
    ev.add_argument("--output", type=Path, default=None, help="also write the markdown report here")
    ev.set_defaults(handler=_eval)

    bn = commands.add_parser("bench", help="per-stage latency and memory on this machine")
    bn.add_argument("--stages", default="stt,llm,tts", help="comma-separated: stt,llm,tts")
    bn.add_argument("--runs", type=int, default=3, help="runs per stage; the first is reported as cold")
    bn.add_argument("--audio", type=Path, default=None, help="16-bit PCM WAV to transcribe (default: macOS say)")
    bn.add_argument("--output", type=Path, default=None, help="also write the markdown report here")
    bn.set_defaults(handler=_bench)

    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    sys.exit(main())
