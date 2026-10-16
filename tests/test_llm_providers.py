"""
Tests for the provider registry and the provider-neutral LLM client.

No network calls are made — the HTTP layer and the Anthropic SDK are patched.
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from tests.conftest import reset_test_db  # noqa: F401 — in-memory DB

from orion.llm import LLMUnavailable, PROVIDERS, Transport, complete_text, resolve


class ProviderRegistryTests(unittest.TestCase):
    def test_all_four_requested_providers_exist(self) -> None:
        """Gemini, ChatGPT, Claude and a free local option are all selectable."""
        for name in ("gemini", "openai", "claude", "ollama"):
            self.assertIn(name, PROVIDERS)

    def test_aliases_resolve(self) -> None:
        """Natural names map onto canonical providers."""
        self.assertEqual(resolve("chatgpt").name, "openai")
        self.assertEqual(resolve("anthropic").name, "claude")
        self.assertEqual(resolve("google").name, "gemini")
        self.assertEqual(resolve("local").name, "ollama")

    def test_resolve_is_case_and_space_insensitive(self) -> None:
        self.assertEqual(resolve("  ChatGPT  ").name, "openai")

    def test_unknown_provider_lists_valid_options(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            resolve("gpt-9000")
        message = str(ctx.exception)
        self.assertIn("claude", message)
        self.assertIn("ollama", message)

    def test_claude_uses_native_transport_not_openai_shim(self) -> None:
        spec = resolve("claude")
        self.assertIs(spec.transport, Transport.ANTHROPIC)
        self.assertEqual(spec.livekit_plugin, "anthropic")
        self.assertIsNone(spec.base_url)

    def test_claude_opts_out_of_temperature(self) -> None:
        """Anthropic models reject `temperature` — the spec must say so."""
        self.assertFalse(resolve("claude").supports_temperature)
        self.assertTrue(resolve("gemini").supports_temperature)

    def test_local_provider_needs_no_key(self) -> None:
        spec = resolve("ollama")
        self.assertFalse(spec.requires_key)
        self.assertTrue(spec.is_local)
        self.assertEqual(spec.api_key(), "")

    def test_cloud_providers_declare_their_key_env(self) -> None:
        self.assertEqual(resolve("claude").api_key_env, "ANTHROPIC_API_KEY")
        self.assertEqual(resolve("openai").api_key_env, "OPENAI_API_KEY")
        self.assertEqual(resolve("gemini").api_key_env, "GOOGLE_API_KEY")

    def test_model_env_override(self) -> None:
        with patch.dict(os.environ, {"ORION_LLM_MODEL": "claude-opus-5"}):
            self.assertEqual(resolve("claude").model, "claude-opus-5")

    def test_utility_model_defaults_to_model(self) -> None:
        """Providers without a cheaper utility model reuse the main one."""
        claude = resolve("claude")
        self.assertEqual(claude.utility, claude.model)
        # Gemini declares a separate, cheaper utility model.
        self.assertNotEqual(resolve("gemini").utility, resolve("gemini").model)


class CompleteTextTests(unittest.IsolatedAsyncioTestCase):
    def _patch_http(self, content: str = "hi"):
        """Patch httpx so we can capture the outgoing OpenAI-compatible payload."""
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": content}}]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        patcher = patch("orion.llm.client.httpx.AsyncClient", return_value=mock_client)
        return patcher, mock_client

    async def test_openai_compat_sends_temperature_and_bearer(self) -> None:
        patcher, mock_client = self._patch_http("result text")
        with patcher, patch.dict(os.environ, {"GOOGLE_API_KEY": "fake-key"}):
            out = await complete_text(
                system="sys", user="usr", provider="gemini", temperature=0.1
            )

        self.assertEqual(out, "result text")
        _, kwargs = mock_client.post.call_args
        self.assertEqual(kwargs["json"]["temperature"], 0.1)
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer fake-key")

    async def test_local_provider_sends_no_auth_header(self) -> None:
        patcher, mock_client = self._patch_http()
        with patcher:
            await complete_text(system="sys", user="usr", provider="ollama")

        _, kwargs = mock_client.post.call_args
        self.assertNotIn("Authorization", kwargs["headers"])

    async def test_missing_key_raises_llm_unavailable(self) -> None:
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            with self.assertRaises(LLMUnavailable):
                await complete_text(system="s", user="u", provider="claude")

    async def test_anthropic_omits_temperature_and_hoists_system(self) -> None:
        """Claude must get `system` as a top-level param and no temperature."""
        from anthropic.types import TextBlock

        # A real TextBlock, so the client's isinstance narrowing is exercised.
        fake_message = MagicMock()
        fake_message.content = [
            TextBlock(type="text", text="claude says hi", citations=None)
        ]

        fake_client = MagicMock()
        fake_client.messages.create = AsyncMock(return_value=fake_message)

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-fake"}):
            with patch("anthropic.AsyncAnthropic", return_value=fake_client):
                out = await complete_text(
                    system="you are a planner",
                    user="plan this",
                    provider="claude",
                    temperature=0.1,
                )

        self.assertEqual(out, "claude says hi")
        kwargs = fake_client.messages.create.call_args.kwargs
        self.assertEqual(kwargs["system"], "you are a planner")
        self.assertNotIn("temperature", kwargs)
        self.assertIn("max_tokens", kwargs)
        self.assertEqual(kwargs["messages"], [{"role": "user", "content": "plan this"}])


if __name__ == "__main__":
    unittest.main()
