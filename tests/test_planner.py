"""
Tests for the LLM-based task planner.

All tests mock the HTTP layer so no real LLM calls are made.
The planner is tested in isolation from the engine.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import AsyncMock, patch, MagicMock

from tests.conftest import reset_test_db  # noqa: F401 — in-memory DB

from orion.core.planner import LLMPlanner, TaskPlan, PlannedAction
from orion.core.engine import default_registry
from orion.core.registry import ToolRegistry


def _make_llm_response(content: str) -> dict:
    """Build a fake OpenAI-compatible chat completion response."""
    return {
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _make_plan_json(steps: list[dict], reasoning: str = "test") -> str:
    """Build a valid plan JSON string."""
    return json.dumps({"reasoning": reasoning, "steps": steps})


class PlannerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        reset_test_db()
        self.registry = default_registry()
        self.planner = LLMPlanner(registry=self.registry, llm_provider="gemini")

    async def test_single_step_intent(self) -> None:
        """A simple intent should produce exactly 1 step with the right tool."""
        plan_json = _make_plan_json(
            steps=[
                {
                    "name": "echo_greeting",
                    "description": "Echo a greeting",
                    "tool_name": "echo_tool",
                    "tool_args": {"message": "hello"},
                }
            ],
            reasoning="Simple greeting, just echo it back",
        )
        mock_response = _make_llm_response(plan_json)

        with patch("orion.core.planner.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.json.return_value = mock_response
            mock_resp.raise_for_status = MagicMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            # Force non-dev mode by patching config
            with patch("orion.core.planner._get_api_key", return_value="fake-key"):
                plan = await self.planner.plan("hello")

        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].tool_name, "echo_tool")
        self.assertEqual(plan.steps[0].tool_args["message"], "hello")
        self.assertIn("greeting", plan.reasoning.lower())

    async def test_two_step_intent(self) -> None:
        """A multi-part intent should produce 2 steps in logical order."""
        plan_json = _make_plan_json(
            steps=[
                {
                    "name": "check_email",
                    "description": "Check the inbox first",
                    "tool_name": "echo_tool",
                    "tool_args": {"message": "checking email"},
                },
                {
                    "name": "send_reply",
                    "description": "Send an email reply",
                    "tool_name": "mock_send_email",
                    "tool_args": {
                        "to": "priya@example.com",
                        "subject": "Re: deadline",
                        "body": "I'll handle it",
                    },
                },
            ],
            reasoning="Read first, then send reply",
        )
        mock_response = _make_llm_response(plan_json)

        with patch("orion.core.planner.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.json.return_value = mock_response
            mock_resp.raise_for_status = MagicMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            with patch("orion.core.planner._get_api_key", return_value="fake-key"):
                plan = await self.planner.plan("check my email and reply to Priya")

        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(plan.steps[0].tool_name, "echo_tool")
        self.assertEqual(plan.steps[1].tool_name, "mock_send_email")
        self.assertEqual(plan.steps[1].tool_args["to"], "priya@example.com")

    async def test_unparseable_response_falls_back(self) -> None:
        """If the LLM returns garbage, the planner falls back to echo_tool."""
        mock_response = _make_llm_response("This is not JSON at all, just random text.")

        with patch("orion.core.planner.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.json.return_value = mock_response
            mock_resp.raise_for_status = MagicMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            with patch("orion.core.planner._get_api_key", return_value="fake-key"):
                plan = await self.planner.plan("do something")

        # Should NOT crash — should fallback
        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].tool_name, "echo_tool")
        self.assertIn("do something", plan.steps[0].tool_args["message"])

    async def test_unknown_tool_falls_back(self) -> None:
        """If the LLM references an unregistered tool, fall back to echo."""
        plan_json = _make_plan_json(
            steps=[
                {
                    "name": "launch_rocket",
                    "description": "Launch a rocket",
                    "tool_name": "nonexistent_rocket_launcher",
                    "tool_args": {"destination": "mars"},
                }
            ],
            reasoning="Tool doesn't exist",
        )
        mock_response = _make_llm_response(plan_json)

        with patch("orion.core.planner.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.json.return_value = mock_response
            mock_resp.raise_for_status = MagicMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            with patch("orion.core.planner._get_api_key", return_value="fake-key"):
                plan = await self.planner.plan("launch a rocket to mars")

        # Should detect unknown tool and fall back
        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].tool_name, "echo_tool")

    async def test_no_api_key_falls_back(self) -> None:
        """If no API key is configured, fall back gracefully."""
        with patch("orion.core.planner._get_api_key", return_value=""):
            # Ensure we're not in dev mode
            with patch("orion.config.config") as mock_cfg:
                mock_cfg.dev_mode = False
                mock_cfg.mock_openclaw = False
                plan = await self.planner.plan("test without key")

        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].tool_name, "echo_tool")

    async def test_network_error_falls_back(self) -> None:
        """If the LLM call fails with a network error, fall back gracefully."""
        import httpx

        with patch("orion.core.planner.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.ConnectError("Connection refused")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            with patch("orion.core.planner._get_api_key", return_value="fake-key"):
                plan = await self.planner.plan("check my calendar")

        # Should NOT crash
        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].tool_name, "echo_tool")


if __name__ == "__main__":
    unittest.main()
