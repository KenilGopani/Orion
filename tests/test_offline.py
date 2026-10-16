"""
Offline mode: the config profile refuses anything that needs the internet,
the local LiveKit server is attached to or supervised, and the Talk panel
gets room tokens for whichever LiveKit is in use.
"""

from __future__ import annotations

import io
import socket
import stat
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stderr
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from livekit import api

from tests.conftest import local_client, make_app

from orion.cli import main as cli_main
from orion.config import config
from orion.offline import LOCAL_LIVEKIT_KEY, LocalLiveKit, offline_problems, use_local_livekit

LOCAL = replace(
    config,
    stt_provider="parakeet_local",
    tts_provider="kokoro",
    llm_provider="ollama",
    parakeet_local_url="http://127.0.0.1:8090/v1",
    kokoro_url="http://127.0.0.1:8880/v1",
    openclaw_url="http://127.0.0.1:18789",
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class OfflineProfileTests(unittest.TestCase):
    def test_all_local_config_is_ready(self) -> None:
        self.assertEqual(offline_problems(LOCAL), [])

    def test_cloud_providers_are_named(self) -> None:
        problems = " ".join(offline_problems(
            replace(LOCAL, stt_provider="deepgram", tts_provider="elevenlabs", llm_provider="gemini")
        ))
        self.assertIn("STT_PROVIDER=deepgram", problems)
        self.assertIn("TTS_PROVIDER=elevenlabs", problems)
        self.assertIn("LLM_PROVIDER=gemini", problems)

    def test_remote_servers_are_flagged(self) -> None:
        problems = " ".join(offline_problems(
            replace(LOCAL, kokoro_url="http://gpu-box.lan:8880/v1", openclaw_url="http://10.0.0.5:18789")
        ))
        self.assertIn("gpu-box.lan", problems)
        self.assertIn("OPENCLAW_API_URL", problems)

    def test_cli_refuses_offline_with_cloud_providers(self) -> None:
        """Nothing starts (no LiveKit, no server) when the profile isn't met."""
        err = io.StringIO()
        with (
            patch.object(config, "llm_provider", "gemini"),
            patch.object(config, "stt_provider", "groq"),
            patch.object(config, "dev_mode", True),
            patch("orion.offline.LocalLiveKit.start") as start,
            redirect_stderr(err),
        ):
            code = cli_main(["up", "--offline", "--no-voice"])
        self.assertEqual(code, 2)
        start.assert_not_called()
        self.assertIn("LLM_PROVIDER=gemini", err.getvalue())
        self.assertIn("STT_PROVIDER=groq", err.getvalue())


class LocalLiveKitTests(unittest.TestCase):
    def test_attaches_to_a_running_server(self) -> None:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            server = LocalLiveKit(port=listener.getsockname()[1], binary="definitely-not-installed")
            server.start()  # no binary needed: something is already listening
            self.assertIsNone(server.proc)

    def test_missing_binary_explains_how_to_install(self) -> None:
        server = LocalLiveKit(port=_free_port(), binary="definitely-not-installed")
        with self.assertRaisesRegex(RuntimeError, "brew install livekit"):
            server.start()

    def test_starts_and_stops_the_server(self) -> None:
        port = _free_port()
        with tempfile.TemporaryDirectory() as tmp:
            # A stand-in livekit-server: listens on the port until terminated.
            fake = Path(tmp) / "livekit-server"
            fake.write_text(textwrap.dedent(f"""\
                #!{sys.executable}
                import socket, sys, time
                assert sys.argv[1:] == ["--dev", "--bind", "127.0.0.1"], sys.argv
                s = socket.socket(); s.bind(("127.0.0.1", {port})); s.listen()
                time.sleep(60)
            """))
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
            server = LocalLiveKit(port=port, binary=str(fake))
            server.start(timeout=10)
            self.assertIsNotNone(server.proc)
            proc = server.proc
            server.stop()
            self.assertIsNotNone(proc.poll(), "server process should be stopped")

    def test_point_config_at_local_server(self) -> None:
        cfg = replace(config)
        use_local_livekit(cfg, LocalLiveKit(port=7880))
        self.assertEqual((cfg.livekit_url, cfg.livekit_api_key), ("ws://127.0.0.1:7880", LOCAL_LIVEKIT_KEY))


class VoiceTokenTests(unittest.TestCase):
    def test_token_grants_the_voice_room(self) -> None:
        cfg = replace(config, enable_scheduler=False, livekit_url="ws://127.0.0.1:7880",
                      livekit_api_key="devkey", livekit_api_secret="secret-" + "x" * 32, voice_room="orion")
        body = local_client(make_app(cfg)).get("/api/voice/token").json()
        self.assertEqual((body["url"], body["room"]), ("ws://127.0.0.1:7880", "orion"))

        claims = api.TokenVerifier("devkey", cfg.livekit_api_secret).verify(body["token"])
        self.assertTrue(claims.identity.startswith("orion-user-"))
        self.assertTrue(claims.video.room_join)
        self.assertEqual(claims.video.room, "orion")

    def test_unconfigured_livekit_is_a_clear_503(self) -> None:
        cfg = replace(config, enable_scheduler=False, livekit_url="", livekit_api_key="", livekit_api_secret="")
        response = local_client(make_app(cfg)).get("/api/voice/token")
        self.assertEqual(response.status_code, 503)
        self.assertIn("LiveKit isn't configured", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
