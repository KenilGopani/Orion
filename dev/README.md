# Dev Tools

Development utilities for working on Orion without external dependencies.

---

## Files

| File | Purpose | Replaces |
|---|---|---|
| `mock_openclaw.py` | Fake OpenClaw server with hardcoded responses | Real OpenClaw daemon |
| `text_agent.py` | CLI interface for testing the engine via typed text | LiveKit voice agent |

---

## Quick Start

```bash
# Option 1: Use make (recommended)
make dev              # Starts text agent with DEV_MODE=true, MOCK_OPENCLAW=true

# Option 2: Run manually
# Terminal 1 — start the mock OpenClaw server
uv run python dev/mock_openclaw.py

# Terminal 2 — start the text agent
DEV_MODE=true MOCK_OPENCLAW=true uv run python dev/text_agent.py
```

---

## Mock OpenClaw Server (`mock_openclaw.py`)

A lightweight FastAPI server that mimics OpenClaw's OpenAI-compatible API:

- **Port**: 18789 (same as real OpenClaw)
- **Endpoints**:
  - `POST /v1/chat/completions` — returns keyword-matched mock responses
  - `GET /v1/models` — returns `mock-openclaw` model
  - `GET /health` — returns `{"status": "ok", "mode": "mock"}`
- **No API keys needed** — all responses are hardcoded
- **Supports**: email, calendar, messaging, file, browser, code, system, and memory keywords

**Adding mock responses for new tools:**

Edit the `MOCK_RESPONSES` dict in `mock_openclaw.py`:

```python
MOCK_RESPONSES = {
    # Add your keyword → response mapping
    "your_keyword": "Your mock response text, sir.",
}
```

---

## Text Agent (`text_agent.py`)

A terminal-based Orion interface that tests the full execution engine:

- **Commands**:
  - Type any voice command (e.g., "check my email", "send email to Priya")
  - `tasks` — list recent tasks and their statuses
  - `events` — show event stream for the last task
  - `health` — check system connectivity
  - `exit` — quit

- **Approval flow**: When a tool requires approval (e.g., `send_email`), the agent prompts you interactively

- **No dependencies on**: LiveKit, STT, LLM, TTS, or any API keys
