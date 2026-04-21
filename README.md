# Orion

### Advanced Voice-first AI Agent

A **voice-first AI agent** that uses [LiveKit](https://livekit.io) for the voice pipeline and [OpenClaw](https://openclaw.ai) as the execution backbone. Talk to Orion naturally — he'll check your email, message your contacts, manage your calendar, run code, and more.

> **"Orion, check my emails and summarize what's urgent."**
> **"Orion, message Priya on WhatsApp that I'll be 10 minutes late."**
> **"Orion, what's on my calendar tomorrow?"**

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

### 4. Run Orion (3 terminals)

**Terminal 1 — OpenClaw Gateway** (if not running as a service):
```bash
openclaw gateway --port 18789
```

**Terminal 2 — MCP Tool Server**:
```bash
uv run orion_server
```

**Terminal 3 — Voice Agent**:
```bash
uv run orion_voice
```

Then open the [LiveKit Agents Playground](https://agents-playground.livekit.io) and connect to your room. Start talking to Orion!

---

## Project Structure

```
orion/
├── pyproject.toml              # uv project config & dependencies
├── .env.example                # Environment template
├── server.py                   # FastMCP server (uv run orion_server)
├── agent.py                    # LiveKit voice agent (uv run orion_voice)
│
├── bridge/                     # OpenClaw communication layer
│   ├── openclaw_client.py      # Async HTTP client → OpenClaw gateway
│   ├── task_router.py          # Intent classification (logging)
│   └── response_parser.py     # Cleans output for TTS
│
└── orion/                     # Core application
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

If you want the LLM to have a purpose-built tool with typed parameters:

1. Create a new file in `orion/tools/` (e.g. `music.py`)
2. Follow the existing pattern:

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

3. Register it in `orion/tools/__init__.py`:

```python
from orion.tools import music  # add import

def register_all_tools(mcp):
    # ... existing registrations ...
    music.register(mcp)  # add this line
```

4. Restart the MCP server. Done.

---

## Provider Configuration

### STT (Speech-to-Text)

| Provider | Env Var | Model | Notes |
|----------|---------|-------|-------|
| **Groq** (default) | `GROQ_API_KEY` | whisper-large-v3 | Free tier, fast |
| OpenAI Whisper | `OPENAI_API_KEY` | whisper-1 | Reliable, paid |
| Sarvam | `SARVAM_API_KEY` | saaras:v3 | Good for Indian accents |
| Deepgram | `DEEPGRAM_API_KEY` | nova-2 | Low latency |

### LLM (Language Model)

| Provider | Env Var | Model | Notes |
|----------|---------|-------|-------|
| **Gemini** (default) | `GOOGLE_API_KEY` | gemini-2.5-flash | Free tier, fast |
| OpenAI | `OPENAI_API_KEY` | gpt-4o | Best quality |
| Groq | `GROQ_API_KEY` | llama-3.3-70b | Free, open source |

### TTS (Text-to-Speech)

| Provider | Env Var | Voice | Notes |
|----------|---------|-------|-------|
| **ElevenLabs** (default) | `ELEVEN_API_KEY` | Adam (British) | Best quality |
| OpenAI | `OPENAI_API_KEY` | onyx | Good, composable |
| Sarvam | `SARVAM_API_KEY` | rahul | Indian English |

Set your preferred providers in `.env`:
```bash
STT_PROVIDER=groq
LLM_PROVIDER=gemini
TTS_PROVIDER=elevenlabs
```

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

Make sure the MCP server is running before starting the voice agent:
```bash
uv run orion_server  # Terminal 2 — must start first
uv run orion_voice   # Terminal 3 — starts after
```

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
FastMCP Server    │ Python / FastMCP   │ :8000  (orion_server)
LiveKit Voice     │ Python / LiveKit   │ LiveKit Cloud
──────────────────┼────────────────────┼──────────────────────

VOICE FLOW:   Mic → VAD → STT → LLM → [Tool?] → TTS → Speaker
TOOL FLOW:    LLM Tool Call → FastMCP → OpenClawClient → Gateway → Result
```

---

## License

MIT
