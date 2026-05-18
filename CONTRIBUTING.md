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

Fill in your `.env` file and start all 3 processes:

```bash
# Terminal 1: OpenClaw (or use mock: make mock-openclaw)
openclaw gateway --port 18789

# Terminal 2: MCP Tool Server
make server

# Terminal 3: Voice Agent
make voice
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

1. **Create a tool module** in `orion/tools/` (e.g., `music.py`):

```python
from bridge import openclaw_client

def register(mcp):
    @mcp.tool()
    async def play_music(song: str, artist: str = "") -> str:
        """Play a song."""
        task = f"Play '{song}'"
        if artist:
            task += f" by {artist}"
        result = await openclaw_client.send_task(task)
        return result["result"]
```

2. **Register it** in `orion/tools/__init__.py`:

```python
from orion.tools import music  # add import

def register_all_tools(mcp):
    # ... existing registrations ...
    music.register(mcp)  # add this line
```

3. **Add mock responses** in `dev/mock_openclaw.py` for your new tool.

4. **Restart** the MCP server (`make server`). Done.

---

## What NOT to Do

- **Don't call OpenClaw directly for side-effectful tools** — route through the approval gate in `orion/core/runtime.py`
- **Don't store secrets in code** — use environment variables via `orion/config.py`
- **Don't break `dev/mock_openclaw.py` compatibility** — new tools should have mock responses
- **Don't merge to `main` without tests passing** — run `make test` first
- **Don't skip the commit convention** — it keeps the git log readable

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
make server        # Start MCP server (production)
make voice         # Start voice agent (production)
make api           # Start REST API (production)
make clean         # Remove __pycache__ and .pyc files
```

---

## Questions?

Open an issue or reach out. We're happy to help you get started.
