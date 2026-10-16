"""
Local API protection: the install token on state-changing routes, and the
loopback Host allow-list that defeats DNS rebinding.
"""

from __future__ import annotations

import stat
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from tests.conftest import AUTH, TEST_TOKEN, local_client, make_app, reset_test_db

from orion.api.security import LOOPBACK_HOSTS, _hostname, load_or_create_token
from orion.config import config


class TokenFileTests(unittest.TestCase):
    def test_token_is_created_private_and_reused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "orion" / "api-token"
            first = load_or_create_token(path)
            self.assertGreaterEqual(len(first), 40)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(load_or_create_token(path), first)

    def test_overly_permissive_token_file_is_tightened(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "api-token"
            load_or_create_token(path)
            path.chmod(0o644)
            load_or_create_token(path)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_empty_token_file_is_regenerated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "api-token"
            path.write_text("")
            self.assertTrue(load_or_create_token(path))


class ApiTokenTests(unittest.TestCase):
    """Approve / reject / create need the token; reads don't."""

    def setUp(self) -> None:
        reset_test_db()
        self.client = local_client(make_app(replace(config, enable_scheduler=False)))
        self.client.__enter__()
        with patch("orion.tools._openclaw.get_openclaw_client", return_value=AsyncMock()):
            runtime = self.client.app.state.runtime  # type: ignore[attr-defined]
            self.task_id = self.client.portal.call(  # type: ignore[union-attr]
                lambda: runtime.run_tool(
                    "send_email", "email Priya", to="p@x.com", subject="s", body="b"
                )
            ).id

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)

    def _post(self, path: str, headers: dict[str, str] | None = None) -> int:
        return self.client.post(path, json={}, headers=headers or {}).status_code

    def test_state_changing_routes_require_the_token(self) -> None:
        for path in (
            "/api/tasks",
            f"/api/tasks/{self.task_id}/approve",
            f"/api/tasks/{self.task_id}/reject",
        ):
            with self.subTest(path=path, token="missing"):
                self.assertEqual(self._post(path), 401)
            with self.subTest(path=path, token="wrong"):
                self.assertEqual(self._post(path, {"X-Orion-Token": "nope"}), 401)

    def test_valid_token_is_accepted(self) -> None:
        response = self.client.post(f"/api/tasks/{self.task_id}/reject", json={}, headers=AUTH)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "FAILED")

    def test_rejected_request_leaves_the_task_untouched(self) -> None:
        self._post(f"/api/tasks/{self.task_id}/approve", {"X-Orion-Token": "nope"})
        task = self.client.get(f"/api/tasks/{self.task_id}").json()
        self.assertEqual(task["status"], "AWAITING_APPROVAL")

    def test_reads_and_token_endpoint_need_no_token(self) -> None:
        self.assertEqual(self.client.get("/api/tasks").status_code, 200)
        self.assertEqual(self.client.get("/api/auth/token").json(), {"token": TEST_TOKEN})


class HostAllowListTests(unittest.TestCase):
    """A DNS-rebinding page sends its own name as Host; it must be refused everywhere."""

    def setUp(self) -> None:
        self.app = make_app(replace(config, enable_scheduler=False))

    def test_foreign_host_is_refused(self) -> None:
        client = TestClient(self.app, base_url="http://evil.example:8000")
        for path in ("/api/auth/token", "/api/tasks", "/", "/mcp/sse"):
            with self.subTest(path=path):
                self.assertEqual(client.get(path).status_code, 421)

    def test_loopback_names_are_allowed(self) -> None:
        for base in ("http://127.0.0.1:8000", "http://localhost:8000", "http://localhost"):
            with self.subTest(base=base):
                client = TestClient(self.app, base_url=base)
                self.assertEqual(client.get("/api/health").status_code, 200)

    def test_host_header_parsing(self) -> None:
        # TestClient can't send an IPv6 Host, so check the parser directly.
        self.assertEqual(_hostname("[::1]:8000"), "[::1]")
        self.assertEqual(_hostname("127.0.0.1:8000"), "127.0.0.1")
        self.assertEqual(_hostname("localhost"), "localhost")
        self.assertIn(_hostname("[::1]:8000"), LOOPBACK_HOSTS)
        self.assertNotIn(_hostname("127.0.0.1.evil.example:8000"), LOOPBACK_HOSTS)

    def test_extra_allowed_hosts_are_configurable(self) -> None:
        app = make_app(replace(config, enable_scheduler=False, allowed_hosts=["orion.lan"]))
        client = TestClient(app, base_url="http://orion.lan")
        self.assertEqual(client.get("/api/health").status_code, 200)


class CorsTests(unittest.TestCase):
    def test_foreign_origin_gets_no_cors_grant(self) -> None:
        """Without a CORS grant, another site can neither read the token nor send the header."""
        client = local_client(make_app(replace(config, enable_scheduler=False)))
        response = client.options(
            "/api/tasks/x/approve",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "x-orion-token",
            },
        )
        self.assertNotIn("access-control-allow-origin", response.headers)


if __name__ == "__main__":
    unittest.main()
