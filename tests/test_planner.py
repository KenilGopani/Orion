"""
Tests for the LLM-based task planner.

The planner is tested in isolation from both the engine and the network:
``orion.llm.complete_text`` is patched, so these tests cover plan parsing
and fallback behaviour regardless of which provider is configured.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import AsyncMock, patch

from tests.conftest import reset_test_db  # noqa: F401 — in-memory DB

from orion.core.engine import default_registry
from orion.core.planner import LLMPlanner
from orion.llm import LLMUnavailable


def _make_plan_json(steps: list[dict], reasoning: str = "test") -> str:
    """Build a valid plan JSON string."""
    return json.dumps({"reasoning": reasoning, "steps": steps})


def _patch_llm(*, returns: str | None = None, raises: Exception | None = None):
    """Patch the planner's LLM call with a canned response or failure."""
    mock = AsyncMock(side_effect=raises) if raises else AsyncMock(return_value=returns)
    return patch("orion.core.planner.complete_text", mock)


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

        with _patch_llm(returns=plan_json):
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

        with _patch_llm(returns=plan_json):
            plan = await self.planner.plan("check my email and reply to Priya")

        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(plan.steps[0].tool_name, "echo_tool")
        self.assertEqual(plan.steps[1].tool_name, "mock_send_email")
        self.assertEqual(plan.steps[1].tool_args["to"], "priya@example.com")

    async def test_markdown_fenced_response_is_parsed(self) -> None:
        """A plan wrapped in ```json fences should still parse."""
        plan_json = _make_plan_json(
            steps=[
                {
                    "name": "echo",
                    "description": "Echo it",
                    "tool_name": "echo_tool",
                    "tool_args": {"message": "fenced"},
                }
            ]
        )

        with _patch_llm(returns=f"```json\n{plan_json}\n```"):
            plan = await self.planner.plan("fenced")

        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].tool_args["message"], "fenced")

    async def test_unparseable_response_falls_back(self) -> None:
        """If the LLM returns garbage, the planner falls back to echo_tool."""
        with _patch_llm(returns="This is not JSON at all, just random text."):
            plan = await self.planner.plan("do something")

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

        with _patch_llm(returns=plan_json):
            plan = await self.planner.plan("launch a rocket to mars")

        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].tool_name, "echo_tool")

    async def test_missing_credentials_falls_back(self) -> None:
        """A provider with no API key degrades to the echo fallback."""
        with _patch_llm(raises=LLMUnavailable("GOOGLE_API_KEY is not set")):
            plan = await self.planner.plan("test without key")

        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].tool_name, "echo_tool")

    async def test_network_error_falls_back(self) -> None:
        """If the LLM call fails with a network error, fall back gracefully."""
        with _patch_llm(raises=LLMUnavailable("connection refused")):
            plan = await self.planner.plan("check my calendar")

        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].tool_name, "echo_tool")

    async def test_unknown_provider_falls_back(self) -> None:
        """A bogus provider name must not crash the engine."""
        planner = LLMPlanner(registry=self.registry, llm_provider="not-a-provider")
        plan = await planner.plan("anything")

        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].tool_name, "echo_tool")


if __name__ == "__main__":
    unittest.main()
