"""
The voice agent wires each local speech provider to its OpenAI-compatible
server with the right model, voice and format.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import tests.conftest  # noqa: F401 — keep the developer's .env out of tests

import agent


class LocalSpeechProviderTests(unittest.TestCase):
    def test_parakeet_local_targets_the_bundled_server(self) -> None:
        with patch.object(agent, "STT_PROVIDER", "parakeet_local"):
            stt = agent._build_stt()
        self.assertEqual(stt._opts.model, "mlx-community/parakeet-tdt-0.6b-v3")
        self.assertEqual(str(stt._client.base_url), "http://127.0.0.1:8090/v1/")

    def test_mlx_audio_requests_wav(self) -> None:
        """mlx-audio needs ffmpeg for the plugin's default MP3, but not for WAV."""
        with patch.object(agent, "TTS_PROVIDER", "mlx_audio"):
            tts = agent._build_tts()
        self.assertEqual(tts._opts.response_format, "wav")
        self.assertEqual(tts._opts.model, "mlx-community/Kokoro-82M-bf16")
        self.assertEqual(tts._opts.voice, "af_heart")
        self.assertEqual(str(tts._client.base_url), "http://127.0.0.1:8881/v1/")

    def test_parakeet_gets_a_batch_endpointing_delay(self) -> None:
        with patch.object(agent, "STT_PROVIDER", "parakeet_local"):
            self.assertEqual(agent._endpointing_delay(), 0.2)

    def test_unknown_providers_fail_clearly(self) -> None:
        with patch.object(agent, "STT_PROVIDER", "nope"), self.assertRaises(ValueError):
            agent._build_stt()
        with patch.object(agent, "TTS_PROVIDER", "nope"), self.assertRaises(ValueError):
            agent._build_tts()


if __name__ == "__main__":
    unittest.main()
