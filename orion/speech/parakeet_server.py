"""
OpenAI-compatible transcription server for NVIDIA Parakeet on Apple Silicon.

``parakeet-mlx`` has no HTTP server of its own, so this wraps it in the one
endpoint Orion's speech pipeline speaks:

    POST /v1/audio/transcriptions   (multipart: file, model, language, prompt,
                                     response_format) → {"text": "..."}

The voice agent then uses it exactly like any other OpenAI-compatible STT
(``STT_PROVIDER=parakeet_local``), with no extra dependency in the agent.

Run it with ``orion parakeet-server`` (needs ``uv sync --extra parakeet``).
"""

from __future__ import annotations

import logging
import tempfile
import wave
from collections.abc import Callable
from pathlib import Path

import numpy as np

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse

from orion.api.security import LoopbackHostMiddleware

logger = logging.getLogger("orion.parakeet")

DEFAULT_MODEL = "mlx-community/parakeet-tdt-0.6b-v3"
DEFAULT_PORT = 8090

#: Transcribes the audio file at a path and returns its text.
Transcriber = Callable[[Path], str]


def create_parakeet_app(transcribe: Transcriber, model_id: str = DEFAULT_MODEL) -> FastAPI:
    """Build the server around ``transcribe`` (injected so it's testable without MLX)."""
    app = FastAPI(title="Orion Parakeet STT", version="1.0.0")
    app.add_middleware(LoopbackHostMiddleware)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "model": model_id}

    @app.get("/v1/models")
    def models() -> dict[str, object]:
        return {"object": "list", "data": [{"id": model_id, "object": "model"}]}

    @app.post("/v1/audio/transcriptions", response_model=None)
    async def transcriptions(
        file: UploadFile = File(...),
        model: str = Form(""),
        language: str = Form(""),
        prompt: str = Form(""),
        response_format: str = Form("json"),
    ) -> dict[str, str] | PlainTextResponse:
        # model / language / prompt are accepted for compatibility; Parakeet
        # detects the language itself and takes no prompt.
        if response_format not in ("json", "text", "verbose_json"):
            raise HTTPException(400, f"Unsupported response_format: {response_format}")
        suffix = Path(file.filename or "audio.wav").suffix or ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
            tmp.write(await file.read())
            tmp.flush()
            try:
                text = (await run_in_threadpool(transcribe, Path(tmp.name))).strip()
            except Exception as exc:
                logger.exception("Transcription failed")
                raise HTTPException(500, f"Transcription failed: {exc}") from exc
        if response_format == "text":
            return PlainTextResponse(text)
        return {"text": text}

    return app


def decode_wav(path: Path, target_rate: int) -> np.ndarray | None:
    """Decode 16-bit PCM WAV to mono float32 at ``target_rate``.

    LiveKit always sends 16-bit PCM WAV, so this covers the voice pipeline
    without ffmpeg (which parakeet-mlx otherwise shells out to). Returns None
    for anything else, so the caller can fall back to parakeet-mlx's loader.
    """
    try:
        with wave.open(str(path), "rb") as wav:
            if wav.getsampwidth() != 2 or wav.getcomptype() != "NONE":
                return None
            channels, rate = wav.getnchannels(), wav.getframerate()
            frames = wav.readframes(wav.getnframes())
    except (wave.Error, EOFError):
        return None

    samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    if rate != target_rate and len(samples):
        # Linear resampling is plenty for speech recognition.
        duration = len(samples) / rate
        new_len = max(1, round(duration * target_rate))
        samples = np.interp(
            np.linspace(0, len(samples) - 1, new_len), np.arange(len(samples)), samples
        ).astype(np.float32)
    return samples


def load_parakeet(model_id: str = DEFAULT_MODEL) -> Transcriber:
    """Load a Parakeet model with parakeet-mlx (Apple Silicon only)."""
    try:
        import mlx.core as mx
        from parakeet_mlx import from_pretrained
        from parakeet_mlx.audio import get_logmel
    except ImportError as exc:
        raise SystemExit(
            "parakeet-mlx is not installed. On an Apple Silicon Mac run:\n"
            "    uv sync --extra parakeet"
        ) from exc

    logger.info("Loading %s (downloads on first use)…", model_id)
    model = from_pretrained(model_id)
    rate = model.preprocessor_config.sample_rate

    def transcribe(path: Path) -> str:
        samples = decode_wav(path, rate)
        if samples is None:
            # Not 16-bit WAV: parakeet-mlx's own loader handles it (needs ffmpeg).
            return str(model.transcribe(str(path)).text)
        if len(samples) < model.preprocessor_config.hop_length:
            return ""  # too short to contain speech
        mel = get_logmel(mx.array(samples), model.preprocessor_config)
        return str(model.generate(mel)[0].text)

    return transcribe
