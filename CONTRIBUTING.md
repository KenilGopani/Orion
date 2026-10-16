# Contributing to Orion

Thank you for your interest in contributing to Orion! This guide will get you from zero to running in under 5 minutes.

---

## Quickstart — Zero API Keys Needed

```bash
git clone https://github.com/KenilGopani/Orion
cd Orion
make setup    # installs deps, creates .env
make dev      # starts text mode with mock OpenClaw
```

That's it. You'll see a CLI prompt where you can type commands like "check my email" or "send whatsapp to Priya saying hello" and get mock responses.

---

## What You Can Work On Without Any API Keys

| Area | Directory | What It Does |
|---|---|---|
| Execution Engine | `orion/core/` | Task lifecycle, approvals, event system |
| Database Layer | `orion/db/` | Persistence (if adding SQLite) |
| API Routes | `orion/api/` | REST endpoints for tasks and approvals |
| MCP Tools | `orion/tools/` | Tool definitions for LLM function calling |
| Bridge Layer | `bridge/` | OpenClaw communication client |
| Dashboard | `dashboard/` | Frontend UI |
| Tests | `tests/` | Unit and integration tests |
| Dev Tools | `dev/` | Mock servers, text agent, seed scripts |

---

## Full Setup (Voice Features)

For voice interaction, you'll need API keys:

1. **LiveKit Cloud** — [cloud.livekit.io](https://cloud.livekit.io) (free tier)
2. **STT** — Groq API key (free) or OpenAI
3. **LLM** — Google Gemini API key (free tier) or OpenAI
4. **TTS** — ElevenLabs API key (free tier) or OpenAI
5. **OpenClaw** — Install with `npm install -g openclaw@latest`

Fill in your `.env` file, then start OpenClaw and Orion:

```bash
# Terminal 1: OpenClaw (or use mock: make mock-openclaw)
openclaw gateway --port 18789

# Terminal 2: Orion — API, tools, scheduler, dashboard and voice on :8000
make up
```

---

## Branch Strategy

Every phase gets its own branch off `main`. Merge only after tests pass.

```
main
├── phase/0-dev-experience
├── phase/1-cleanup
├── phase/2-sqlite-persistence
├── phase/3-llm-planner
├── phase/4-memory
├── phase/5-dashboard
├── phase/6-scheduler
└── phase/7-tests-ci
```

---

## Commit Convention

```
<type>(<scope>): <short description>
```

| Type | When |
|---|---|
| `feat` | New feature |
| `fix` | Bug fix |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `test` | Adding or updating tests |
| `docs` | Documentation only |
| `chore` | Maintenance (deps, build, config) |
| `ci` | CI/CD changes |

**Examples:**
```
feat(dev-env): add mock OpenClaw server on port 18789
fix(engine): fix circular import in bridge/__init__.py
refactor(tools): route write_file through approval gate
test(planner): add mocked LLM planner tests
docs(contributing): add contributor quickstart guide
chore(deps): add sqlmodel and aiosqlite to pyproject.toml
ci(github): add GitHub Actions workflow for pytest and ruff
```

---

## How to Add a New Tool

Every tool is **one declaration**. The voice tool (MCP), the planner's tool list and the approval gate are all generated from it; there's nothing else to wire up.

1. **Declare the tool** in `orion/tools/` (a new module, or the one for its domain):

```python
# orion/tools/music.py
from pydantic import BaseModel, Field

from orion.core.models import ToolSafetyLevel
from orion.tools._openclaw import openclaw_tool


class PlayMusicInput(BaseModel):
    song: str = Field(description="Song title.")
    artist: str = Field("", description="Artist (optional).")


TOOLS = [
    openclaw_tool(
        name="play_music",
        description="Play a song.",
        input_model=PlayMusicInput,
        safety_level=ToolSafetyLevel.LOW_RISK,
        render=lambda p: f"Play '{p.song}'" + (f" by {p.artist}" if p.artist else ""),
        action="Playing the song",
    ),
]
```

   Choose the safety level deliberately: `EXTERNAL_SIDE_EFFECT` or `DESTRUCTIVE` makes every call wait for human approval. For a tool that doesn't use OpenClaw, build a `ToolDefinition` with your own handler (see `get_time` in `orion/tools/system.py`).

2. **Register a new module** in `all_tools()` in `orion/tools/__init__.py`, and **add the tool to `EXPECTED_SAFETY`** in `tests/test_tool_surface.py` (the test fails until you do).

3. **Add mock responses** in `dev/mock_openclaw.py` for your new tool.

4. **Restart** Orion (`make up`). Done.

---

## What NOT to Do

- **Don't add MCP tools by hand** — declare a `ToolDefinition` in `orion/tools/`; the MCP surface is generated from the registry so every call goes through the approval gate
- **Don't store secrets in code** — use environment variables via `orion/config.py`
- **Don't break `dev/mock_openclaw.py` compatibility** — new tools should have mock responses
- **Don't merge to `main` without tests passing** — run `make test` first
- **Don't skip the commit convention** — it keeps the git log readable

---

## Evals

Changing a prompt, a tool description or the default model? Measure it:

```bash
make eval    # tool-selection accuracy for LLM_PROVIDER
make bench   # per-stage latency and memory
```

To add an eval case, append one JSON line to `evals/tool_selection.jsonl`:

```json
{"id": "slack-3", "kind": "positive", "utterance": "Tell the team channel standup moved to 11.", "expect_tool": "send_slack", "expect_args": {"channel": "team", "message": "11"}}
```

`kind` is `positive` (expects a tool), `negative` (expects no tool) or
`injection` (a `tool_result` carries hostile content; the model must not call a
send or destructive tool). `make test` validates every case against the real
tool schemas.

---

## Running Tests

```bash
make test          # Run all tests
make test-cov      # Run with coverage report
make lint          # Ruff + mypy
make lint-fix      # Auto-fix linting issues
```

---

## Useful Make Targets

```bash
make help          # List all available targets
make dev           # Text mode with mock (no API keys)
make mock-openclaw # Start mock server standalone
make up           # Run Orion: API, tools, scheduler, dashboard, voice (:8000)
make voice         # Run only the voice agent against a running `make up`
make dashboard     # Dashboard dev server with hot reload (proxies /api)
make clean         # Remove __pycache__ and .pyc files
```

---

## Questions?

Open an issue or reach out. We're happy to help you get started.
