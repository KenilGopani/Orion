"""
LLM-based task planner for Orion.

Decomposes a user intent into a sequence of tool calls by asking an LLM
to produce a structured plan. Falls back to a safe ``echo_tool`` step
if the LLM response cannot be parsed, so the engine never crashes.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
from pydantic import BaseModel, Field

from orion.core.registry import ToolRegistry

logger = logging.getLogger("orion.planner")


# ── Models ────────────────────────────────────────────────────────────────────

class PlannedAction(BaseModel):
    """A single step the planner wants the engine to execute."""

    name: str
    description: str
    tool_name: str
    tool_args: dict[str, Any] = Field(default_factory=dict)


class TaskPlan(BaseModel):
    """The full plan returned by the LLM."""

    steps: list[PlannedAction] = Field(default_factory=list)
    reasoning: str = ""


# ── Prompt ────────────────────────────────────────────────────────────────────

_PLAN_SCHEMA = """{
  "reasoning": "<brief explanation of your plan>",
  "steps": [
    {
      "name": "<short step name>",
      "description": "<what this step does>",
      "tool_name": "<exact tool name from the list>",
      "tool_args": { "<arg1>": "<value1>", ... }
    }
  ]
}"""

PLANNER_SYSTEM_PROMPT = """\
You are a task planning AI for Orion, a voice-first AI assistant.
Given a user's intent, decompose it into a sequence of tool calls.

Available tools:
{tool_descriptions}

Rules:
- Only use tools from the list above — use exact tool names
- Order steps logically (read before write, fetch before send)
- For simple single-tool tasks, return exactly 1 step
- For multi-part requests, return multiple steps in order
- Fill in tool_args with reasonable values extracted from the user's intent
- If the intent cannot be accomplished with available tools, return an empty steps list
- Return ONLY valid JSON matching this schema:

{schema}

Respond with ONLY the JSON object. No markdown fences, no explanation outside the JSON.\
"""


# ── Provider endpoints ────────────────────────────────────────────────────────

_PROVIDER_URLS: dict[str, str] = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
    "groq": "https://api.groq.com/openai/v1/chat/completions",
}

_PROVIDER_MODELS: dict[str, str] = {
    "gemini": "gemini-2.0-flash",
    "openai": "gpt-4o-mini",
    "groq": "llama-3.1-70b-versatile",
}


def _get_api_key(provider: str) -> str:
    """Retrieve the API key for the given provider from config."""
    from orion.config import config

    key_map = {
        "gemini": config.google_api_key,
        "openai": config.openai_api_key,
        "groq": config.groq_api_key,
    }
    return key_map.get(provider, "")


# ── Planner ───────────────────────────────────────────────────────────────────

class LLMPlanner:
    """Decomposes user intents into tool call sequences via an LLM."""

    def __init__(
        self,
        registry: ToolRegistry,
        llm_provider: str = "gemini",
    ) -> None:
        self.registry = registry
        self.llm_provider = llm_provider

    def _build_tool_descriptions(self) -> str:
        """Format all registered tools into a readable list for the prompt."""
        lines: list[str] = []
        for tool in self.registry.list_tools():
            # Get the model fields for argument documentation
            schema = tool.input_model.model_json_schema()
            props = schema.get("properties", {})
            args_desc = ", ".join(
                f"{k}: {v.get('type', 'any')}" for k, v in props.items()
            )
            lines.append(
                f"- {tool.name}: {tool.description}\n"
                f"  Safety: {tool.safety_level.value}\n"
                f"  Args: {{{args_desc}}}"
            )
        return "\n".join(lines)

    def _build_system_prompt(self) -> str:
        """Build the complete system prompt with tool descriptions."""
        return PLANNER_SYSTEM_PROMPT.format(
            tool_descriptions=self._build_tool_descriptions(),
            schema=_PLAN_SCHEMA,
        )

    async def plan(self, user_intent: str) -> TaskPlan:
        """Decompose a user intent into a TaskPlan via the configured LLM.

        On any failure (network, parse error, etc.) falls back to a
        safe ``echo_tool`` step so the engine never crashes.
        """
        from orion.config import config

        # In dev mode with mock OpenClaw, route through the local mock server
        if config.dev_mode and config.mock_openclaw:
            return await self._plan_via_openclaw(user_intent, config.openclaw_url)

        # Otherwise, call the real LLM provider
        api_key = _get_api_key(self.llm_provider)
        if not api_key:
            logger.warning(
                "No API key for LLM provider '%s' — falling back to echo",
                self.llm_provider,
            )
            return self._fallback_plan(user_intent)

        return await self._plan_via_llm(user_intent, api_key)

    async def _plan_via_llm(self, user_intent: str, api_key: str) -> TaskPlan:
        """Call a cloud LLM provider for planning."""
        url = _PROVIDER_URLS.get(self.llm_provider)
        model = _PROVIDER_MODELS.get(self.llm_provider)

        if not url or not model:
            logger.warning("Unknown LLM provider '%s'", self.llm_provider)
            return self._fallback_plan(user_intent)

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": self._build_system_prompt()},
                {"role": "user", "content": user_intent},
            ],
            "temperature": 0.1,  # Low temperature for deterministic planning
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            raw = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            return self._parse_plan(raw, user_intent)

        except Exception as exc:
            logger.warning("LLM planner call failed: %s — falling back to echo", exc)
            return self._fallback_plan(user_intent)

    async def _plan_via_openclaw(self, user_intent: str, base_url: str) -> TaskPlan:
        """Route planning through the local mock/real OpenClaw server."""
        system_prompt = self._build_system_prompt()
        payload = {
            "model": "openclaw",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_intent},
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{base_url.rstrip('/')}/v1/chat/completions",
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()

            raw = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            return self._parse_plan(raw, user_intent)

        except Exception as exc:
            logger.warning("OpenClaw planner call failed: %s — falling back", exc)
            return self._fallback_plan(user_intent)

    def _parse_plan(self, raw_text: str, user_intent: str) -> TaskPlan:
        """Parse the LLM's JSON response into a TaskPlan.

        If parsing fails or the plan references unknown tools,
        falls back to the safe echo plan.
        """
        try:
            # Strip markdown fences if present
            cleaned = raw_text.strip()
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
            cleaned = cleaned.strip()

            plan = TaskPlan.model_validate_json(cleaned)

            # Validate that all referenced tools exist in the registry
            for step in plan.steps:
                try:
                    self.registry.get(step.tool_name)
                except KeyError:
                    logger.warning(
                        "Planner referenced unknown tool '%s' — falling back",
                        step.tool_name,
                    )
                    return self._fallback_plan(user_intent)

            if not plan.steps:
                return self._fallback_plan(user_intent)

            logger.info(
                "Planned %d step(s) for intent: %s — %s",
                len(plan.steps),
                user_intent[:60],
                plan.reasoning[:80],
            )
            return plan

        except Exception as exc:
            logger.warning("Failed to parse LLM plan: %s — falling back", exc)
            return self._fallback_plan(user_intent)

    def _fallback_plan(self, user_intent: str) -> TaskPlan:
        """Return a safe single-step plan that echoes the intent."""
        return TaskPlan(
            reasoning="Fallback: could not produce a multi-step plan",
            steps=[
                PlannedAction(
                    name="echo_intent",
                    description="Echo the user intent (fallback)",
                    tool_name="echo_tool",
                    tool_args={"message": user_intent},
                )
            ],
        )
