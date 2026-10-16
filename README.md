# Orion

[![CI](https://github.com/KenilGopani/Orion/actions/workflows/ci.yml/badge.svg)](https://github.com/KenilGopani/Orion/actions/workflows/ci.yml)

### Advanced Voice-first AI Agent

A **voice-first AI agent** that uses [LiveKit](https://livekit.io) for the voice pipeline and [OpenClaw](https://openclaw.ai) as the execution backbone. Talk to Orion naturally — he'll check your email, message your contacts, manage your calendar, run code, and more.

> **"Orion, check my emails and summarize what's urgent."**
> **"Orion, message Priya on WhatsApp that I'll be 10 minutes late."**
> **"Orion, what's on my calendar tomorrow?"**

What separates Orion from a chatbot with plugins is the **approval gate**: every
tool carries a safety level, and anything irreversible — sending a message,
overwriting a file, running a shell command — halts and waits for a human before
it executes. Approve it in the dashboard and Orion tells you, by voice, whether it
went through. Every decision is written to an append-only event log.

> 🔒 **Security model:** [SECURITY.md](SECURITY.md) covers the threat model, what
> Orion mitigates (prompt injection, CSRF, DNS rebinding) and what it can't.
>
> 📖 **New to the codebase?** Read **[ARCHITECTURE.md](ARCHITECTURE.md)** — a full
> walkthrough of the request flows, the approval gate, every service and how they
> interact, plus a candid list of known rough edges.

---

## How It Works

```
  🎤 Microphone
       │
       ▼
┌──────────────────────────────────────────────────────────┐
│                  VOICE PIPELINE (Python)                  │
│                                                          │
│   Silero VAD → STT (Whisper/Groq) → LLM (Gemini/GPT)   │
│                                        │                 │
│                           ┌────────────┘                 │
│                           ▼                              │
│                    MCP Tool Call?                         │
│                     │         │                          │
│                    Yes        No                         │
│                     │         │                          │
│                     ▼         ▼                          │
│              OpenClaw Bridge  Direct Answer              │
│                     │         │                          │
│                     ▼         ▼                          │
│                   TTS (ElevenLabs/OpenAI)                │
└──────────────────────────────────────────────────────────┘
       │
       ▼
  🔊 Speaker

       ║ (parallel process)
       ▼

┌──────────────────────────────────────────────────────────┐
│              OPENCLAW GATEWAY (Local Daemon)              │
│                                                          │
│   📧 Email    💬 Messaging   📅 Calendar   💻 Code      │
│   📁 Files    🌐 Browser     ⚙️  System    🧠 Memory    │
│                                                          │
│          Port 18789 · OpenAI-Compatible API              │
└──────────────────────────────────────────────────────────┘
```

## What Orion Can Do

Orion is designed to be a highly capable, extensible, and action-oriented assistant:

- **Broad Toolset**: All tools delegate to OpenClaw, allowing Orion to act as a powerful system agent.
- **Read & Write Actions**: Orion doesn't just fetch information; he can send messages, manage calendar events, read/write files, and run code.
- **Unlimited Extensibility**: Adding new capabilities requires zero code changes. Simply install an OpenClaw skill, and Orion instantly learns how to use it.
- **Composed Persona**: Orion maintains a composed, precise, and professional demeanor, keeping responses brief and action-focused.

---

## Prerequisites

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** — Fast Python package manager
- **Node.js 22+** — Required for OpenClaw
- **[OpenClaw](https://openclaw.ai)** — The AI agent daemon
- **[LiveKit Cloud](https://cloud.livekit.io)** account — For voice streaming
- API keys for at least one provider in each category:
  - **STT**: Groq (free) / OpenAI / Sarvam / Deepgram
  - **LLM**: Google Gemini (free tier) / OpenAI / Groq
  - **TTS**: ElevenLabs / OpenAI / Sarvam

---

## Setup

### 1. Clone and Install

```bash
git clone https://github.com/yourusername/orion
cd orion
uv sync
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your API keys
```

### 3. Install and Start OpenClaw

```bash
# Install OpenClaw
npm install -g openclaw@latest

# Run onboarding (configures workspace, model, channels)
openclaw onboard --install-daemon

# Start the gateway
openclaw gateway --port 18789

# Verify it's running
openclaw gateway status
```

### 4. Run Orion

Start the OpenClaw gateway (skip this if it runs as a service):
```bash
openclaw gateway --port 18789
```

Recommended: give Orion least-privilege OpenClaw agents, so read-only tools can never exec or write (see [SECURITY.md](SECURITY.md#setting-up-least-privilege-openclaw-agents)):
```bash
uv run orion openclaw-config   # prints the agent definitions and checks your OpenClaw config
```

Then start Orion with one command:
```bash
make up        # or: uv run orion up
```

That single process serves everything on port 8000 and starts the voice agent:

| URL | What |
|---|---|
| http://127.0.0.1:8000/ | Dashboard: tasks, approvals, conversation log |
| http://127.0.0.1:8000/api | REST API used by the dashboard |
| http://127.0.0.1:8000/mcp/sse | MCP tools used by the voice agent |

Use `orion up --no-voice` to run without the voice agent. Voice is also skipped, with a warning, when the LiveKit credentials aren't set.

Open the [LiveKit Agents Playground](https://agents-playground.livekit.io) and connect to your room. Start talking to Orion!

---

## Project Structure

```
orion/
├── pyproject.toml              # uv project config & dependencies
├── .env.example                # Environment template
├── agent.py                    # LiveKit voice agent (started by `orion up`)
│
├── bridge/                     # OpenClaw communication layer
│   ├── openclaw_client.py      # Async HTTP client → OpenClaw gateway
│   ├── task_router.py          # Intent classification (logging)
│   └── response_parser.py     # Cleans output for TTS
│
└── orion/                     # Core application
    ├── app.py                  # The one ASGI app: /api, /mcp, dashboard, scheduler
    ├── cli.py                  # `orion up`
    ├── config.py               # Typed config from env vars
    ├── persona.py              # System prompt loader
    ├── prompts/
    │   └── system_prompt.txt   # Orion character prompt
    └── tools/                  # MCP tools (one file per domain)
        ├── email.py            # check_email, send_email, summarize_inbox
        ├── messaging.py        # send_whatsapp, send_telegram, send_slack
        ├── calendar.py         # get_events, create_event, reschedule
        ├── code.py             # create_project, run_code, open_editor
        ├── files.py            # read_file, write_file, search_files
        ├── browser.py          # open_url, search_web, take_screenshot
        ├── system.py           # get_time, get_system_info, run_command
        └── memory.py           # remember_this, recall, forget
```

---

## Adding New Capabilities

The beauty of the OpenClaw architecture: **adding a new capability requires zero code changes** to the voice pipeline.

### Option A: Install an OpenClaw Skill (easiest)

OpenClaw skills extend its capabilities automatically. If a new skill is available:

```bash
openclaw skills install <skill-name>
```

Orion will automatically be able to use it — OpenClaw handles routing.

### Option B: Add a Dedicated Orion Tool (for better UX)

If you want the LLM to have a purpose-built tool with typed parameters, declare it once. The voice tool, the planner's tool list and the approval gate all come from that declaration:

1. Declare it once in `orion/tools/` (a new module, or the one for its domain):

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

2. If it's a new module, add it to `all_tools()` in `orion/tools/__init__.py`, and add the tool to `EXPECTED_SAFETY` in `tests/test_tool_surface.py`.

3. Restart Orion (`make up`). Done.

---

## Provider Configuration

### STT (Speech-to-Text)

| Provider | Env Var | Model | Notes |
|----------|---------|-------|-------|
| **whisper_local** (default) | *none* | whisper-large-v3-turbo | **Free**, fully local, no API key |
| Groq | `GROQ_API_KEY` | whisper-large-v3 | Free tier, fast |
| OpenAI Whisper | `OPENAI_API_KEY` | whisper-1 | Reliable, paid |
| Sarvam | `SARVAM_API_KEY` | saaras:v3 | Good for Indian accents |
| Deepgram | `DEEPGRAM_API_KEY` | nova-2 | Low latency |

### LLM (Language Model)

| Provider | Alias | Env Var | Model | Notes |
|----------|-------|---------|-------|-------|
| **Gemini** (default) | `google` | `GOOGLE_API_KEY` | gemini-2.5-flash | Free tier, fast |
| OpenAI | `chatgpt` | `OPENAI_API_KEY` | gpt-4o | Best general quality |
| Claude | `anthropic` | `ANTHROPIC_API_KEY` | claude-sonnet-5 | Strongest tool use |
| Groq | — | `GROQ_API_KEY` | llama-3.3-70b | Free tier, fastest |
| Ollama | `local` | *none* | qwen2.5:7b | **Free**, fully local |

Switching is one env var:

```bash
LLM_PROVIDER=claude     # or gemini / chatgpt / groq / ollama
```

All five are defined in a single registry at
[`orion/llm/providers.py`](orion/llm/providers.py) — the voice agent, the task
planner, and memory extraction all resolve from that one table, so adding a
provider means adding one `ProviderSpec` and nothing else.

Override a model without touching the registry:

```bash
ORION_LLM_MODEL=claude-opus-5
```

**Two transports.** Gemini, OpenAI, Groq and Ollama share one OpenAI-compatible
HTTP path (the same code, a different `base_url`). Claude uses the official
`anthropic` SDK and the native LiveKit Anthropic plugin — deliberately *not* an
OpenAI-compatibility shim, since the Messages API is the supported path for tool
use. The registry also records that Anthropic models reject `temperature`, so
the shared client omits it for Claude instead of sending a parameter that would
return a 400.

**For a fully free stack**, install [Ollama](https://ollama.com) and pull a model:

```bash
ollama pull qwen2.5:7b
```

Then set `LLM_PROVIDER=ollama`. Combined with `whisper_local` and `kokoro`, Orion
runs with **zero API keys** apart from LiveKit transport.

### TTS (Text-to-Speech)

| Provider | Env Var | Voice | Notes |
|----------|---------|-------|-------|
| **kokoro** (default) | *none* | am_michael | **Free**, fully local, no API key |
| ElevenLabs | `ELEVEN_API_KEY` | Adam (British) | Best quality, 10k chars/mo free |
| OpenAI | `OPENAI_API_KEY` | onyx | Good, composable |
| Sarvam | `SARVAM_API_KEY` | rahul | Indian English |

Set your preferred providers in `.env`:
```bash
STT_PROVIDER=whisper_local
LLM_PROVIDER=gemini
TTS_PROVIDER=kokoro
```

### Running the free local speech stack

The two local providers are OpenAI-compatible HTTP servers you run yourself, so
they need **no extra Python dependencies** — the existing `openai` plugin just
points at `localhost`.

**Whisper STT** — [whisper.cpp](https://github.com/ggml-org/whisper.cpp) is
Metal-accelerated on Apple Silicon:

```bash
whisper-server -m models/ggml-large-v3-turbo.bin --port 8080
```

**Kokoro TTS** — [kokoro-fastapi](https://github.com/remsky/Kokoro-FastAPI):

```bash
docker run -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-cpu
```

Neither model streams, but LiveKit handles that automatically: it segments mic
audio with Silero VAD before calling Whisper, and wraps Kokoro in a
`tts.StreamAdapter` with a sentence tokenizer so playback starts after the first
sentence rather than the full response.

> **Note:** local STT/TTS removes the OpenAI/Groq/ElevenLabs keys, but LiveKit
> Cloud credentials are still required for voice transport.

---

## Troubleshooting

### "OpenClaw isn't responding"

```bash
# Check if the gateway is running
openclaw gateway status

# Start it if it's not
openclaw gateway --port 18789

# Check logs for errors
openclaw logs --follow
```

### "MCP Server connection refused"

The voice agent reaches its tools at `http://127.0.0.1:8000/mcp/sse`. `orion up` starts both, so this usually means the voice agent was started on its own (`make voice`) without `make up` running, or `ORION_PORT` differs between the two.

### "LiveKit connection error"

1. Verify your LiveKit credentials in `.env`
2. Check that `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET` are set
3. Try the [LiveKit Agents Playground](https://agents-playground.livekit.io) to test connectivity

### "ElevenLabs voice error"

Make sure `ELEVEN_API_KEY` is set and your `ELEVENLABS_VOICE_ID` is valid. Default voice is Adam (`pNInz6obpgDQGcFmaJgB`).

### Tool calls leaking into speech

If you hear raw function names or JSON in Orion's voice, switch the LLM provider:
```bash
LLM_PROVIDER=gemini  # or openai — Groq sometimes leaks tool calls
```

---

## Architecture Reference

```
COMPONENT         │ TECHNOLOGY         │ PORT / PROCESS
──────────────────┼────────────────────┼──────────────────────
OpenClaw Gateway  │ Node.js            │ :18789 (daemon)
Orion app         │ Python / FastAPI   │ :8000  (orion up: /, /api, /mcp/sse)
LiveKit Voice     │ Python / LiveKit   │ child of orion up → LiveKit Cloud
──────────────────┼────────────────────┼──────────────────────

VOICE FLOW:   Mic → VAD → STT → LLM → [Tool?] → TTS → Speaker
TOOL FLOW:    LLM Tool Call → /mcp → ExecutionEngine → OpenClawClient → Gateway → Result
```

---

## License

MIT
