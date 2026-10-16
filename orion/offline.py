"""
Fully offline mode: every model local, and a self-hosted LiveKit server
instead of LiveKit Cloud for the audio transport.

``orion up --offline`` checks that nothing configured needs the internet,
then attaches to (or starts) ``livekit-server --dev`` on 127.0.0.1 and points
the voice agent and the built-in Talk panel at it.

LiveKit's dev mode uses well-known credentials (``devkey`` / ``secret``), so
the server is bound to loopback only; nothing off this machine can reach it.
"""

from __future__ import annotations

import logging
import shutil
import socket
import subprocess
import time
from urllib.parse import urlparse

from orion.config import Config

logger = logging.getLogger("orion.offline")

LOCAL_LIVEKIT_PORT = 7880
LOCAL_LIVEKIT_KEY = "devkey"  # livekit-server --dev's built-in credentials
LOCAL_LIVEKIT_SECRET = "secret"

LOCAL_STT = {"whisper_local", "parakeet_local"}
LOCAL_TTS = {"kokoro", "mlx_audio"}
_LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def _is_loopback(url: str) -> bool:
    return (urlparse(url).hostname or "") in _LOOPBACK


def offline_problems(cfg: Config) -> list[str]:
    """Everything in ``cfg`` that would need the internet. Empty means offline-ready."""
    from orion.llm import resolve

    problems: list[str] = []
    if cfg.stt_provider not in LOCAL_STT:
        problems.append(f"STT_PROVIDER={cfg.stt_provider} is a cloud service; use whisper_local or parakeet_local.")
    else:
        url = cfg.whisper_local_url if cfg.stt_provider == "whisper_local" else cfg.parakeet_local_url
        if not _is_loopback(url):
            problems.append(f"The STT server ({url}) isn't on this machine.")

    if cfg.tts_provider not in LOCAL_TTS:
        problems.append(f"TTS_PROVIDER={cfg.tts_provider} is a cloud service; use kokoro or mlx_audio.")
    else:
        url = cfg.kokoro_url if cfg.tts_provider == "kokoro" else cfg.mlx_audio_url
        if not _is_loopback(url):
            problems.append(f"The TTS server ({url}) isn't on this machine.")

    try:
        spec = resolve(cfg.llm_provider)
    except ValueError as exc:
        problems.append(str(exc))
    else:
        if not spec.is_local:
            problems.append(f"LLM_PROVIDER={cfg.llm_provider} is a cloud service; use ollama.")
        elif spec.base_url and not _is_loopback(spec.base_url):
            problems.append(f"Ollama ({spec.base_url}) isn't on this machine.")

    if not _is_loopback(cfg.openclaw_url):
        problems.append(f"OPENCLAW_API_URL ({cfg.openclaw_url}) isn't on this machine.")
    return problems


def _port_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


class LocalLiveKit:
    """Attach to, or start and stop, a loopback-only ``livekit-server --dev``."""

    def __init__(self, port: int = LOCAL_LIVEKIT_PORT, binary: str = "livekit-server") -> None:
        self.port = port
        self.binary = binary
        self.proc: subprocess.Popen[bytes] | None = None

    @property
    def url(self) -> str:
        return f"ws://127.0.0.1:{self.port}"

    def start(self, timeout: float = 15) -> None:
        if _port_open(self.port):
            logger.info("Using the LiveKit server already running on %s", self.url)
            return
        path = shutil.which(self.binary)
        if not path:
            raise RuntimeError(
                "Offline mode needs a local LiveKit server. Install it with:\n"
                "    brew install livekit\n"
                "(or see https://docs.livekit.io/home/self-hosting/local/)"
            )
        logger.info("Starting local LiveKit server on %s…", self.url)
        self.proc = subprocess.Popen([path, "--dev", "--bind", "127.0.0.1"])
        deadline = time.monotonic() + timeout
        while not _port_open(self.port):
            if self.proc.poll() is not None:
                raise RuntimeError(f"livekit-server exited with code {self.proc.returncode}")
            if time.monotonic() > deadline:
                self.stop()
                raise RuntimeError(f"livekit-server didn't open port {self.port} within {timeout:.0f}s")
            time.sleep(0.2)

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None


def use_local_livekit(cfg: Config, server: LocalLiveKit) -> None:
    """Point ``cfg`` (voice agent and Talk panel) at the local LiveKit server."""
    cfg.livekit_url = server.url
    cfg.livekit_api_key = LOCAL_LIVEKIT_KEY
    cfg.livekit_api_secret = LOCAL_LIVEKIT_SECRET
