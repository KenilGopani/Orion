"""
The single-process app: one engine, everything mounted on one port, and no
work done merely by importing Orion's modules.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from mcp import ClientSession
from mcp.client.sse import sse_client
from starlette.routing import Mount

from tests.conftest import AUTH, live_server, local_client, make_app, reset_test_db

from orion.app import MCP_MOUNT_PATH, build_mcp
from orion.config import config
from orion.core.engine import ExecutionEngine
from orion.core.runtime import build_runtime

REPO_ROOT = Path(__file__).resolve().parent.parent


class SingleProcessAppTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_test_db()
        self.cfg = replace(config, enable_scheduler=False)

    def test_exactly_one_engine_per_app(self) -> None:
        with patch.object(ExecutionEngine, "__init__", autospec=True, wraps=ExecutionEngine.__init__) as init:
            app = make_app(self.cfg)
            with local_client(app) as client:
                client.get("/api/health")
        self.assertEqual(init.call_count, 1)

    def test_api_and_tools_share_the_runtime(self) -> None:
        app = make_app(self.cfg)
        with local_client(app) as client:
            created = client.post("/api/tasks", json={"user_intent": "echo hello"}, headers=AUTH).json()
            # The task the API created is visible through the same runtime the tools use.
            self.assertIsNotNone(app.state.runtime.store.get_task(created["id"]))
            listed = client.get("/api/tasks").json()
        self.assertIn(created["id"], [t["id"] for t in listed])

    def test_mcp_is_mounted_on_the_same_app(self) -> None:
        app = make_app(self.cfg)
        mounts = [r.path for r in app.routes if isinstance(r, Mount)]
        self.assertIn(MCP_MOUNT_PATH, mounts)

    def test_root_serves_the_dashboard_or_a_hint(self) -> None:
        with local_client(make_app(self.cfg)) as client:
            response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])


class McpToolSurfaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_voice_tools_are_registered(self) -> None:
        tools = await build_mcp(build_runtime()).list_tools()
        self.assertEqual(len(tools), 24)


class McpOverSseTests(unittest.IsolatedAsyncioTestCase):
    """A real MCP client against a real server: catches mount-path bugs that
    in-process tests can't (the SSE stream never ends, and the message URL the
    server advertises must resolve under /mcp)."""

    def setUp(self) -> None:
        reset_test_db()
        self.server = live_server(make_app(replace(config, enable_scheduler=False)))
        self.base_url = self.server.__enter__()

    def tearDown(self) -> None:
        self.server.__exit__(None, None, None)

    async def test_client_lists_and_calls_tools(self) -> None:
        async def session() -> tuple[int, str]:
            async with sse_client(f"{self.base_url}{MCP_MOUNT_PATH}/sse") as (read, write):
                async with ClientSession(read, write) as client:
                    await client.initialize()
                    tools = (await client.list_tools()).tools
                    result = await client.call_tool("get_time", {})
                    return len(tools), result.content[0].text

        tool_count, text = await asyncio.wait_for(session(), timeout=20)
        self.assertEqual(tool_count, 24)
        self.assertIn("current local time", text)


class ImportSideEffectTests(unittest.TestCase):
    def test_importing_orion_touches_no_files(self) -> None:
        """Importing the runtime and app must not create the database."""
        with tempfile.TemporaryDirectory() as home:
            env = {**os.environ, "HOME": home}
            subprocess.run(
                [sys.executable, "-c", "import orion.core.runtime, orion.app, orion.cli"],
                cwd=REPO_ROOT,
                env=env,
                check=True,
            )
            self.assertFalse((Path(home) / ".orion").exists())


if __name__ == "__main__":
    unittest.main()
