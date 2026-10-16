"""
The Parakeet wrapper speaks the OpenAI transcription contract that LiveKit's
STT plugin uses. A fake transcriber stands in for parakeet-mlx, so this runs
anywhere (including Linux CI, where MLX isn't available).
"""

from __future__ import annotations

import io
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

from fastapi.testclient import TestClient

from orion.speech.parakeet_server import DEFAULT_MODEL, create_parakeet_app, decode_wav


def _wav_bytes() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 1600)
    return buffer.getvalue()


class ParakeetServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.received: list[bytes] = []

        def transcribe(path: Path) -> str:
            self.received.append(path.read_bytes())
            return "  check my email  "

        self.client = TestClient(create_parakeet_app(transcribe), base_url="http://127.0.0.1:8090")

    def _post(self, **form: str):
        # Exactly the request livekit-plugins-openai sends.
        return self.client.post(
            "/v1/audio/transcriptions",
            files={"file": ("file.wav", _wav_bytes(), "audio/wav")},
            data={"model": DEFAULT_MODEL, "language": "", "prompt": "", **form},
        )

    def test_json_transcription(self) -> None:
        response = self._post(response_format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"text": "check my email"})
        self.assertEqual(self.received, [_wav_bytes()], "the uploaded audio reaches the model unchanged")

    def test_text_transcription(self) -> None:
        response = self._post(response_format="text")
        self.assertEqual(response.text, "check my email")

    def test_unsupported_format_is_rejected(self) -> None:
        self.assertEqual(self._post(response_format="srt").status_code, 400)

    def test_transcriber_errors_become_500s(self) -> None:
        def broken(path: Path) -> str:
            raise RuntimeError("model crashed")

        client = TestClient(create_parakeet_app(broken), base_url="http://127.0.0.1:8090")
        response = client.post(
            "/v1/audio/transcriptions", files={"file": ("file.wav", _wav_bytes(), "audio/wav")}
        )
        self.assertEqual(response.status_code, 500)
        self.assertIn("model crashed", response.json()["detail"])

    def test_models_and_health(self) -> None:
        self.assertEqual(self.client.get("/v1/models").json()["data"][0]["id"], DEFAULT_MODEL)
        self.assertEqual(self.client.get("/health").json()["status"], "ok")

    def test_only_loopback_hosts(self) -> None:
        client = TestClient(create_parakeet_app(lambda p: ""), base_url="http://evil.example")
        self.assertEqual(client.get("/health").status_code, 421)


class DecodeWavTests(unittest.TestCase):
    """LiveKit sends 16-bit PCM WAV; decoding it in Python avoids needing ffmpeg."""

    def _write(self, samples: np.ndarray, rate: int, channels: int = 1, width: int = 2) -> Path:
        path = Path(self.tmp.name) / f"a{rate}_{channels}_{width}.wav"
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(width)
            wav.setframerate(rate)
            wav.writeframes(samples.tobytes())
        return path

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_mono_16k_passes_through(self) -> None:
        pcm = np.array([0, 16384, -16384, 32767], dtype="<i2")
        out = decode_wav(self._write(pcm, 16000), 16000)
        assert out is not None
        np.testing.assert_allclose(out, [0, 0.5, -0.5, 32767 / 32768], atol=1e-6)
        self.assertEqual(out.dtype, np.float32)

    def test_stereo_is_mixed_to_mono(self) -> None:
        pcm = np.array([16384, 0, 16384, 0], dtype="<i2")  # L=0.5, R=0 per frame
        out = decode_wav(self._write(pcm, 16000, channels=2), 16000)
        assert out is not None
        np.testing.assert_allclose(out, [0.25, 0.25], atol=1e-6)

    def test_resampled_to_the_model_rate(self) -> None:
        one_second_48k = np.zeros(48000, dtype="<i2")
        out = decode_wav(self._write(one_second_48k, 48000), 16000)
        assert out is not None
        self.assertEqual(len(out), 16000)

    def test_unsupported_audio_falls_back(self) -> None:
        eight_bit = self._write(np.zeros(100, dtype=np.uint8), 16000, width=1)
        self.assertIsNone(decode_wav(eight_bit, 16000))
        not_wav = Path(self.tmp.name) / "x.mp3"
        not_wav.write_bytes(b"ID3 not really audio")
        self.assertIsNone(decode_wav(not_wav, 16000))


if __name__ == "__main__":
    unittest.main()
