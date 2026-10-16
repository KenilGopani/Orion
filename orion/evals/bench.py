"""
Per-stage latency benchmark for the voice pipeline on this machine.

For each configured stage it measures what a user feels:

- **STT**: seconds to transcribe a ~5 s utterance
- **LLM**: time to first token (cold vs warm prompt cache) and total, with
  the voice agent's full tool list and persona in the prompt
- **TTS**: time to first audio byte, and total, for a short reply

…plus the chip, RAM, and resident memory of each local model server.
Run with ``make bench``.
"""

from __future__ import annotations

import json
import platform
import shutil
import statistics
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import httpx

from orion.config import Config
from orion.evals.llm import ToolSpec, Turn, openai_messages
from orion.llm.providers import ProviderSpec, Transport

UTTERANCE = "Orion, check my email and tell Priya on WhatsApp that I will be ten minutes late."
REPLY = "You have three unread emails. The most urgent is from Priya about tomorrow's deadline."

STT_SERVERS = {  # provider → (config url attr, config model attr)
    "whisper_local": ("whisper_local_url", "whisper_local_model"),
    "parakeet_local": ("parakeet_local_url", "parakeet_model"),
}
TTS_SERVERS = {  # provider → (url attr, model attr or literal, voice attr, response format)
    "kokoro": ("kokoro_url", "kokoro", "kokoro_voice", "mp3"),
    "mlx_audio": ("mlx_audio_url", "mlx_audio_model", "mlx_audio_voice", "wav"),
}


@dataclass
class StageResult:
    stage: str
    provider: str
    model: str
    cold: float | None = None
    warm: list[float] = field(default_factory=list)
    first_cold: float | None = None  # LLM first token / TTS first byte, cold run
    first_warm: list[float] = field(default_factory=list)
    memory_mb: float | None = None
    error: str = ""


# ── Machine facts ─────────────────────────────────────────────────────────────

def _sysctl(name: str) -> str:
    try:
        return subprocess.run(["sysctl", "-n", name], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def machine_info() -> dict[str, str]:
    mem = _sysctl("hw.memsize")
    return {
        "chip": _sysctl("machdep.cpu.brand_string") or platform.processor() or platform.machine(),
        "ram": f"{int(mem) / 2**30:.0f} GB" if mem.isdigit() else "unknown",
        "os": f"{platform.system()} {platform.release()}",
        "python": platform.python_version(),
    }


def rss_mb_for_url(url: str) -> float | None:
    """Resident memory of the local process listening on ``url``'s port, if any."""
    parsed = urlparse(url)
    if parsed.hostname not in ("127.0.0.1", "localhost") or not parsed.port or not shutil.which("lsof"):
        return None
    try:
        pids = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{parsed.port}", "-sTCP:LISTEN", "-t"],
            capture_output=True, text=True, check=False,
        ).stdout.split()
        if not pids:
            return None
        rss_kb = subprocess.run(
            ["ps", "-o", "rss=", "-p", pids[0]], capture_output=True, text=True, check=True
        ).stdout.strip()
        return int(rss_kb) / 1024
    except (OSError, ValueError, subprocess.CalledProcessError):
        return None


def sample_wav() -> bytes:
    """A ~5 s spoken utterance as 16-bit 16 kHz WAV (macOS ``say``), the format LiveKit sends."""
    if not (shutil.which("say") and shutil.which("afconvert")):
        raise RuntimeError("No speech sample: pass --audio path/to/clip.wav (16-bit PCM WAV).")
    with tempfile.TemporaryDirectory() as tmp:
        aiff, wav = Path(tmp) / "u.aiff", Path(tmp) / "u.wav"
        subprocess.run(["say", "-o", str(aiff), UTTERANCE], check=True)
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(aiff), str(wav)], check=True)
        return wav.read_bytes()


# ── Stages ────────────────────────────────────────────────────────────────────

async def bench_stt(url: str, model: str, wav: bytes, runs: int, api_key: str = "local") -> list[float]:
    """Seconds per transcription, first run first."""
    times = []
    async with httpx.AsyncClient(base_url=url.rstrip("/") + "/", timeout=120) as client:
        for _ in range(runs):
            started = time.monotonic()
            resp = await client.post(
                "audio/transcriptions",
                files={"file": ("file.wav", wav, "audio/wav")},
                data={"model": model, "response_format": "json"},
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()
            times.append(time.monotonic() - started)
    return times


async def bench_llm(
    spec: ProviderSpec, system: str, tools: list[ToolSpec], runs: int
) -> list[tuple[float, float]]:
    """(time to first token, total) per streamed completion, first run first."""
    if spec.transport is Transport.ANTHROPIC:
        return await _bench_anthropic(spec, system, tools, runs)
    payload = {
        "model": spec.model,
        "messages": openai_messages(system, [Turn("user", UTTERANCE)]),
        "tools": [{"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}} for t in tools],
        "stream": True,
    }
    headers = {"Authorization": f"Bearer {spec.api_key()}"} if spec.api_key() else {}
    results = []
    async with httpx.AsyncClient(timeout=180) as client:
        for _ in range(runs):
            started, first = time.monotonic(), None
            url = f"{(spec.base_url or '').rstrip('/')}/chat/completions"
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if first is None and line.startswith("data:") and line[5:].strip() != "[DONE]":
                        chunk = json.loads(line[5:])
                        delta = (chunk.get("choices") or [{}])[0].get("delta", {})
                        if delta.get("content") or delta.get("tool_calls"):
                            first = time.monotonic() - started
            total = time.monotonic() - started
            results.append((first if first is not None else total, total))
    return results


async def _bench_anthropic(spec: ProviderSpec, system: str, tools: list[ToolSpec], runs: int) -> list[tuple[float, float]]:
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=spec.api_key())
    results = []
    for _ in range(runs):
        started, first = time.monotonic(), None
        async with client.messages.stream(
            model=spec.model,
            max_tokens=512,
            system=system,
            messages=[{"role": "user", "content": UTTERANCE}],
            tools=[{"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools],  # type: ignore[misc]
        ) as stream:
            async for event in stream:
                if first is None and event.type == "content_block_delta":
                    first = time.monotonic() - started
        total = time.monotonic() - started
        results.append((first if first is not None else total, total))
    return results


async def bench_tts(
    url: str, model: str, voice: str, runs: int, response_format: str = "wav", api_key: str = "local"
) -> list[tuple[float, float]]:
    """(time to first audio byte, total) per synthesis, first run first."""
    results = []
    payload = {"model": model, "input": REPLY, "voice": voice, "response_format": response_format}
    async with httpx.AsyncClient(base_url=url.rstrip("/") + "/", timeout=120) as client:
        for _ in range(runs):
            started, first = time.monotonic(), None
            async with client.stream(
                "POST", "audio/speech", json=payload, headers={"Authorization": f"Bearer {api_key}"}
            ) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes():
                    if first is None and chunk:
                        first = time.monotonic() - started
            total = time.monotonic() - started
            results.append((first if first is not None else total, total))
    return results


# ── Orchestration and report ──────────────────────────────────────────────────

async def _bench_llm_stage(r: StageResult, spec: ProviderSpec, runs: int) -> None:
    from orion.evals import voice_system_prompt, voice_tools

    try:
        tools, _ = await voice_tools()
        timings = await bench_llm(spec, voice_system_prompt(), tools, runs)
        r.first_cold, r.cold = timings[0]
        r.first_warm, r.warm = [t[0] for t in timings[1:]], [t[1] for t in timings[1:]]
        r.memory_mb = rss_mb_for_url(spec.base_url or "") if spec.is_local else None
    except Exception as exc:  # report, don't crash the whole bench
        r.error = str(exc) or type(exc).__name__


async def run_bench(cfg: Config, stages: list[str], runs: int, audio: bytes | None = None) -> list[StageResult]:
    from orion.llm import resolve

    results: list[StageResult] = []
    if "stt" in stages:
        url_attr, model_attr = STT_SERVERS.get(cfg.stt_provider, ("", ""))
        r = StageResult("STT", cfg.stt_provider, getattr(cfg, model_attr, "") if model_attr else "")
        if not url_attr:
            r.error = "only local STT providers are benchmarked"
        else:
            url = getattr(cfg, url_attr)
            try:
                times = await bench_stt(url, r.model, audio or sample_wav(), runs)
                r.cold, r.warm, r.memory_mb = times[0], times[1:], rss_mb_for_url(url)
            except Exception as exc:  # report, don't crash the whole bench
                r.error = str(exc) or type(exc).__name__
        results.append(r)

    if "llm" in stages:
        spec = resolve(cfg.llm_provider)
        r = StageResult("LLM", spec.name, spec.model)
        if spec.requires_key and not spec.api_key():
            r.error = f"{spec.api_key_env} is not set"
        else:
            await _bench_llm_stage(r, spec, runs)
        results.append(r)

    if "tts" in stages:
        server = TTS_SERVERS.get(cfg.tts_provider)
        r = StageResult("TTS", cfg.tts_provider, "")
        if not server:
            r.error = "only local TTS providers are benchmarked"
        else:
            url_attr, model, voice_attr, fmt = server
            url, r.model = getattr(cfg, url_attr), getattr(cfg, model, model)
            try:
                timings = await bench_tts(url, r.model, getattr(cfg, voice_attr), runs, fmt)
                r.first_cold, r.cold = timings[0]
                r.first_warm, r.warm = [t[0] for t in timings[1:]], [t[1] for t in timings[1:]]
                r.memory_mb = rss_mb_for_url(url)
            except Exception as exc:
                r.error = str(exc) or type(exc).__name__
        results.append(r)
    return results


def _s(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}s"


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def bench_report(results: list[StageResult], info: dict[str, str], runs: int) -> str:
    lines = [
        f"## Latency benchmark: {info['chip']}, {info['ram']} ({runs} runs per stage)",
        "",
        "| Stage | Provider | Model | First token / byte (cold → warm) | Total (cold → warm) | Memory |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        if r.error:
            lines.append(f"| {r.stage} | {r.provider} | `{r.model}` | — | error: {r.error[:80]} | — |")
            continue
        first = "—" if r.first_cold is None else f"{_s(r.first_cold)} → {_s(_median(r.first_warm))}"
        mem = "—" if r.memory_mb is None else f"{r.memory_mb:,.0f} MB"
        lines.append(
            f"| {r.stage} | {r.provider} | `{r.model}` | {first} | "
            f"{_s(r.cold)} → {_s(_median(r.warm))} | {mem} |"
        )
    lines += ["", f"_{info['os']}, Python {info['python']}. Warm = median of runs after the first._"]
    return "\n".join(lines) + "\n"
