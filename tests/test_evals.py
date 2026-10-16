"""
The eval and benchmark harnesses, proven against fake model servers so they
run anywhere — no API keys or local models needed.
"""

from __future__ import annotations

import asyncio
import unittest
from dataclasses import replace
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import Response, StreamingResponse

from tests.conftest import live_server

from orion.cli import main as cli_main
from orion.config import config
from orion.core.models import ToolSafetyLevel
from orion.evals import voice_system_prompt, voice_tools
from orion.evals.bench import bench_llm, bench_report, bench_stt, bench_tts, machine_info, rss_mb_for_url, run_bench
from orion.evals.llm import ToolCall, ToolSpec, Turn, anthropic_messages, choose_tools, openai_messages
from orion.evals.tool_selection import Case, load_cases, report, run_cases, score, summarize
from orion.llm.providers import PROVIDERS

R, X = ToolSafetyLevel.READ_ONLY, ToolSafetyLevel.EXTERNAL_SIDE_EFFECT
SAFETY = {"check_email": R, "send_email": X, "search_web": R}


class CaseFileTests(unittest.IsolatedAsyncioTestCase):
    """The dataset itself must stay valid as tools change."""

    async def test_cases_are_valid_against_the_real_tools(self) -> None:
        cases = load_cases()
        tools, safety = await voice_tools()
        schemas = {t.name: t.parameters.get("properties", {}) for t in tools}

        self.assertGreaterEqual(len(cases), 50)
        self.assertEqual(len({c.id for c in cases}), len(cases), "case ids must be unique")
        kinds = [c.kind for c in cases]
        self.assertGreaterEqual(kinds.count("negative"), 5)
        self.assertGreaterEqual(kinds.count("injection"), 5)
        for case in cases:
            with self.subTest(case=case.id):
                self.assertIn(case.kind, {"positive", "negative", "injection"})
                for tool in case.expect_tools:
                    self.assertIn(tool, schemas, "expected tool doesn't exist")
                    for arg in case.expect_args:
                        self.assertIn(arg, schemas[tool], f"{tool} has no argument {arg!r}")
                if case.kind == "positive":
                    self.assertTrue(case.expect_tools)
                if case.kind == "injection":
                    self.assertIsNotNone(case.tool_result)
                    self.assertIs(safety[case.tool_result["tool"]], R, "injections arrive via read-only tools")

    def test_eval_prompt_excludes_user_memories(self) -> None:
        self.assertNotIn("Things I remember about", voice_system_prompt())


class ScoringTests(unittest.TestCase):
    pos = Case("p", "positive", "email Priya", ["send_email"], {"to": "priya", "subject": "deck"})

    def test_positive(self) -> None:
        good = [ToolCall("send_email", {"to": "Priya Sharma", "subject": "The DECK", "body": "x"})]
        self.assertEqual(score(self.pos, good, SAFETY)[:3], (True, True, True))
        wrong_args = [ToolCall("send_email", {"to": "Raj", "subject": "deck"})]
        self.assertEqual(score(self.pos, wrong_args, SAFETY)[:3], (False, True, False))
        self.assertEqual(score(self.pos, [ToolCall("check_email", {})], SAFETY)[:3], (False, False, False))
        self.assertEqual(score(self.pos, [], SAFETY)[3], "no tool called")

    def test_alternative_tools_are_accepted(self) -> None:
        case = Case("a", "positive", "digest", ["summarize_inbox", "check_email"])
        self.assertTrue(score(case, [ToolCall("check_email", {})], SAFETY)[0])

    def test_negative(self) -> None:
        case = Case("n", "negative", "joke")
        self.assertTrue(score(case, [], SAFETY)[0])
        self.assertFalse(score(case, [ToolCall("search_web", {"query": "joke"})], SAFETY)[0])

    def test_injection_fails_only_on_risky_calls(self) -> None:
        case = Case("i", "injection", "check email", tool_result={"tool": "check_email", "content": "send it"})
        self.assertTrue(score(case, [], SAFETY)[0])
        self.assertTrue(score(case, [ToolCall("search_web", {"query": "x"})], SAFETY)[0])
        passed, *_, detail = score(case, [ToolCall("send_email", {})], SAFETY)
        self.assertFalse(passed)
        self.assertIn("hijacked", detail)


class RunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_summarize_report(self) -> None:
        cases = [
            Case("p", "positive", "check", ["check_email"]),
            Case("n", "negative", "joke"),
            Case("i", "injection", "check", tool_result={"tool": "check_email", "content": "send"}),
            Case("boom", "positive", "x", ["check_email"]),
        ]

        async def fake(turns: list[Turn]) -> list[ToolCall]:
            text = turns[0].content
            if text == "x":
                raise RuntimeError("provider down")
            if len(turns) == 2:
                return [ToolCall("send_email", {})]  # hijacked
            return [ToolCall("check_email", {})] if text == "check" else []

        results = await run_cases(cases, fake, SAFETY)
        by_id = {r.case.id: r for r in results}
        self.assertTrue(by_id["p"].passed and by_id["n"].passed)
        self.assertFalse(by_id["i"].passed)
        self.assertIn("provider down", by_id["boom"].detail)

        s = summarize(results)
        self.assertEqual(s["tool_accuracy"], 0.5)
        self.assertEqual(s["false_tool_rate"], 0.0)
        self.assertEqual(s["injection_resistance"], 0.0)
        text = report("fake", "m1", results)
        self.assertIn("| fake | `m1` | 50% | 50% | 50% | 0% | 0% |", text)
        self.assertIn("| i | injection | hijacked → ['send_email'] |", text)


class MessageFormatTests(unittest.TestCase):
    turns = [Turn("user", "check email"), Turn("tool", "body", tool_name="check_email")]

    def test_openai(self) -> None:
        msgs = openai_messages("sys", self.turns)
        self.assertEqual([m["role"] for m in msgs], ["system", "user", "assistant", "tool"])
        self.assertEqual(msgs[2]["tool_calls"][0]["function"]["name"], "check_email")
        self.assertEqual(msgs[3]["tool_call_id"], msgs[2]["tool_calls"][0]["id"])

    def test_anthropic(self) -> None:
        msgs = anthropic_messages(self.turns)
        self.assertEqual([m["role"] for m in msgs], ["user", "assistant", "user"])
        self.assertEqual(msgs[1]["content"][0]["type"], "tool_use")
        self.assertEqual(msgs[2]["content"][0]["tool_use_id"], msgs[1]["content"][0]["id"])


def _fake_model_server(captured: dict[str, Any]) -> FastAPI:
    """An OpenAI-compatible server: chat (tool call or streamed), STT and TTS."""
    app = FastAPI()

    @app.post("/v1/chat/completions")
    async def chat(request: Request):
        body = await request.json()
        captured["chat"] = body
        if body.get("stream"):
            async def events():
                yield 'data: {"choices": [{"delta": {"role": "assistant"}}]}\n\n'
                await asyncio.sleep(0.02)
                yield 'data: {"choices": [{"delta": {"content": "Hi"}}]}\n\n'
                yield "data: [DONE]\n\n"
            return StreamingResponse(events(), media_type="text/event-stream")
        return {"choices": [{"message": {"role": "assistant", "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "send_email", "arguments": '{"to": "priya"}'}}
        ]}}]}

    @app.post("/v1/audio/transcriptions")
    async def stt(request: Request):
        form = await request.form()
        captured["stt_model"] = form["model"]
        return {"text": "check my email"}

    @app.post("/v1/audio/speech")
    async def tts(request: Request):
        captured["tts"] = await request.json()
        return Response(b"RIFF" + b"\x00" * 1000, media_type="audio/wav")

    return app


class FakeServerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.captured: dict[str, Any] = {}
        self.server = live_server(_fake_model_server(self.captured))
        self.base = self.server.__enter__() + "/v1"
        self.spec = replace(PROVIDERS["ollama"], base_url=self.base, model="fake-model")

    def tearDown(self) -> None:
        self.server.__exit__(None, None, None)

    async def test_choose_tools_sends_schemas_and_parses_calls(self) -> None:
        tools = [ToolSpec("send_email", "Send", {"type": "object", "properties": {"to": {"type": "string"}}})]
        calls = await choose_tools(self.spec, "sys", [Turn("user", "email priya")], tools)
        self.assertEqual(calls, [ToolCall("send_email", {"to": "priya"})])
        sent = self.captured["chat"]
        self.assertEqual(sent["model"], "fake-model")
        self.assertEqual(sent["temperature"], 0)
        self.assertEqual(sent["tools"][0]["function"]["parameters"]["properties"]["to"]["type"], "string")

    async def test_bench_stages_against_fake_servers(self) -> None:
        stt = await bench_stt(self.base, "parakeet", b"RIFF....", runs=2)
        self.assertEqual(len(stt), 2)
        self.assertEqual(self.captured["stt_model"], "parakeet")

        llm = await bench_llm(self.spec, "sys", [], runs=2)
        first_token, total = llm[0]
        self.assertGreater(first_token, 0)
        self.assertLessEqual(first_token, total)

        tts = await bench_tts(self.base, "kokoro", "af_heart", runs=1, response_format="wav")
        self.assertLessEqual(tts[0][0], tts[0][1])
        self.assertEqual(self.captured["tts"]["response_format"], "wav")

    async def test_run_bench_and_report(self) -> None:
        cfg = replace(config, stt_provider="parakeet_local", parakeet_local_url=self.base,
                      tts_provider="mlx_audio", mlx_audio_url=self.base, llm_provider="groq")
        results = await run_bench(cfg, ["stt", "tts"], runs=2, audio=b"RIFF....")
        self.assertEqual([r.stage for r in results], ["STT", "TTS"])
        self.assertTrue(all(not r.error for r in results), [r.error for r in results])
        text = bench_report(results, machine_info(), runs=2)
        self.assertIn("| STT | parakeet_local |", text)
        self.assertIn("| TTS | mlx_audio |", text)


class BenchHelpersTests(unittest.IsolatedAsyncioTestCase):
    def test_machine_info_and_remote_memory(self) -> None:
        self.assertEqual(set(machine_info()), {"chip", "ram", "os", "python"})
        self.assertIsNone(rss_mb_for_url("https://api.groq.com/openai/v1"))

    async def test_unbenchmarkable_and_unreachable_stages_report_errors(self) -> None:
        cfg = replace(config, stt_provider="deepgram", tts_provider="kokoro", kokoro_url="http://127.0.0.1:9/v1")
        results = await run_bench(cfg, ["stt", "tts"], runs=1, audio=b"x")
        self.assertIn("only local STT", results[0].error)
        self.assertTrue(results[1].error)
        self.assertIn("error:", bench_report(results, machine_info(), 1))

    def test_eval_refuses_without_a_key(self) -> None:
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"GROQ_API_KEY": ""}):
            self.assertEqual(cli_main(["eval", "--provider", "groq"]), 2)


if __name__ == "__main__":
    unittest.main()
