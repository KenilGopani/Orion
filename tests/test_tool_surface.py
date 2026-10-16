"""
The voice LLM's MCP surface is generated from the tool registry, so:

- every MCP tool is a registered ToolDefinition with the same arguments,
- every call goes through the engine (a task record plus audit events),
- gated tools never reach OpenClaw before approval,
- and every tool's safety level is a deliberate, reviewed choice.
"""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import AsyncMock, patch

from tests.conftest import reset_test_db

from orion.app import build_mcp
from orion.core.models import ToolSafetyLevel
from orion.core.runtime import build_runtime

R, L, X, D = (
    ToolSafetyLevel.READ_ONLY,
    ToolSafetyLevel.LOW_RISK,
    ToolSafetyLevel.EXTERNAL_SIDE_EFFECT,
    ToolSafetyLevel.DESTRUCTIVE,
)

#: Every voice tool and its safety level. Adding a tool, or changing a level,
#: must update this table, which makes the classification a reviewed decision.
EXPECTED_SAFETY: dict[str, ToolSafetyLevel] = {
    "check_email": R, "send_email": X, "summarize_inbox": R,
    "send_whatsapp": X, "send_telegram": X, "send_slack": X,
    "get_events": R, "create_event": X, "reschedule_event": X,
    "create_project": D, "run_code": D, "open_editor": L,
    "read_file": R, "write_file": D, "search_files": R,
    "open_url": L, "search_web": R, "take_screenshot": R,
    "get_time": R, "get_system_info": R, "run_command": D,
    "remember_this": L, "what_do_i_know_about": R, "forget": L,
}  # fmt: skip


def _sample_args(schema: dict[str, Any]) -> dict[str, Any]:
    """Minimal valid arguments for a tool's JSON schema (required fields only)."""
    samples = {"string": "sample", "integer": 1, "boolean": True}
    props = schema.get("properties", {})
    args = {name: samples[props[name]["type"]] for name in schema.get("required", [])}
    if "url" in args:
        args["url"] = "https://example.com"
    return args


class ToolSurfaceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        reset_test_db()
        self.runtime = build_runtime()
        self.mcp = build_mcp(self.runtime)

    async def test_every_mcp_tool_is_a_registered_tool_with_the_same_arguments(self) -> None:
        mcp_tools = {t.name: t for t in await self.mcp.list_tools()}
        voice_tools = {t.name: t for t in self.runtime.registry.list_tools() if t.voice}

        self.assertEqual(set(mcp_tools), set(voice_tools))
        for name, mcp_tool in mcp_tools.items():
            with self.subTest(tool=name):
                model = voice_tools[name].input_model
                self.assertEqual(set(mcp_tool.inputSchema.get("properties", {})), set(model.model_fields))
                required = {f for f, info in model.model_fields.items() if info.is_required()}
                self.assertEqual(set(mcp_tool.inputSchema.get("required", [])), required)
                self.assertEqual(mcp_tool.description, voice_tools[name].description)

    async def test_argument_descriptions_reach_the_llm(self) -> None:
        tool = next(t for t in await self.mcp.list_tools() if t.name == "send_email")
        self.assertEqual(
            tool.inputSchema["properties"]["to"]["description"], "Recipient email address or name."
        )

    def test_every_voice_tool_has_a_reviewed_safety_level(self) -> None:
        actual = {t.name: t.safety_level for t in self.runtime.registry.list_tools() if t.voice}
        self.assertEqual(actual, EXPECTED_SAFETY)

    def test_voice_cannot_approve_or_reject(self) -> None:
        """Approval must come from a channel the LLM can't drive (SECURITY.md #7)."""
        for tool in self.runtime.registry.list_tools():
            if tool.voice:
                with self.subTest(tool=tool.name):
                    self.assertNotRegex(tool.name, r"approv|reject|grant|confirm|authori[sz]e")

    def test_engine_fallbacks_are_not_exposed_to_voice(self) -> None:
        hidden = {t.name for t in self.runtime.registry.list_tools() if not t.voice}
        self.assertEqual(hidden, {"echo_tool", "mock_send_email"})

    async def test_every_voice_call_runs_through_the_engine(self) -> None:
        client = AsyncMock()
        client.send_task.return_value = {"status": "success", "result": "done"}
        store, events = self.runtime.store, self.runtime.events

        with (
            patch("orion.tools._openclaw.get_openclaw_client", return_value=client),
            patch("orion.tools.memory._extract_key_value", AsyncMock(return_value=("k", "v"))),
        ):
            for tool in await self.mcp.list_tools():
                with self.subTest(tool=tool.name):
                    before = len(store.list_tasks())
                    calls_before = client.send_task.await_count
                    await self.mcp.call_tool(tool.name, _sample_args(tool.inputSchema))

                    tasks = store.list_tasks()
                    self.assertEqual(len(tasks), before + 1, "call did not create a task")
                    task = tasks[-1]
                    self.assertEqual(task.steps[0].planned_tool_name, tool.name)
                    event_types = [e.event_type for e in events.list_events(task.id)]
                    self.assertIn("task_created", event_types)

                    if EXPECTED_SAFETY[tool.name] in (X, D):
                        self.assertEqual(task.status.value, "AWAITING_APPROVAL")
                        self.assertEqual(client.send_task.await_count, calls_before)
                    else:
                        self.assertEqual(task.status.value, "SUCCEEDED")
                        self.assertIn("tool_succeeded", event_types)

    async def test_read_only_call_is_audited_and_answered(self) -> None:
        client = AsyncMock()
        client.send_task.return_value = {"status": "success", "result": "Three unread emails."}
        with patch("orion.tools._openclaw.get_openclaw_client", return_value=client):
            content, _ = await self.mcp.call_tool("check_email", {"count": 3})

        self.assertEqual(content[0].text, "Three unread emails.")
        client.send_task.assert_awaited_once_with(
            "Check my unread emails, get the last 3. Summarize what's urgent or important.",
            agent=None,
        )
        task = self.runtime.store.list_tasks()[-1]
        # The audit record holds the full arguments that ran, defaults included.
        self.assertEqual(
            task.steps[0].planned_tool_args, {"count": 3, "filter": "unread", "summarize": True}
        )

    def test_planner_can_use_read_tools(self) -> None:
        """Scheduled jobs ("check my email…") need read tools in the planner's list."""
        prompt = self.runtime.planner._build_system_prompt()
        for name in ("check_email", "get_events", "summarize_inbox"):
            self.assertIn(f"- {name}:", prompt)


if __name__ == "__main__":
    unittest.main()
