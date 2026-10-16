# Orion — Architecture & Contributor Guide

> A complete walkthrough of what Orion is, why it exists, and exactly what
> happens between a user speaking and something occurring in the real world.
>
> **New here?** Read §1–§4 to get the mental model, then §5 for the request
> flows. §12 lists known rough edges so you don't mistake them for your bugs.

---

## Table of contents

1. [What Orion is](#1-what-orion-is)
2. [The core idea: two brains, one gate](#2-the-core-idea-two-brains-one-gate)
3. [Runtime topology](#3-runtime-topology)
4. [Component map](#4-component-map)
5. [Request flows](#5-request-flows) ← *the heart of this document*
6. [The approval gate](#6-the-approval-gate)
7. [Data model and persistence](#7-data-model-and-persistence)
8. [The LLM layer](#8-the-llm-layer)
9. [The speech layer](#9-the-speech-layer)
10. [The dashboard](#10-the-dashboard)
11. [Development environment](#11-development-environment)
12. [Known rough edges](#12-known-rough-edges)
13. [How to add things](#13-how-to-add-things)

---

## 1. What Orion is

Orion is a **voice-first AI assistant that takes real actions on your machine
and accounts.** You speak; it checks your email, messages people, manages your
calendar, writes files, and runs commands.

The thing that makes Orion more than a thin wrapper around a chatbot is the
**approval gate**. Every capability is tagged with a safety level. Anything that
touches the outside world irreversibly — sending a message, overwriting a file,
running a shell command — cannot execute until a human approves it. Every
decision along the way is written to an append-only event log.

So the project's real purpose is this:

> **Give an LLM real capabilities without giving it unsupervised authority.**

Everything else in the codebase — the task engine, the event store, the
dashboard, the persistence layer — exists to make that guarantee auditable and
operable.

### Three things Orion is not

- **Not a chatbot.** Conversation is the interface, not the product. The output
  is actions taken and recorded.
- **Not an executor itself.** Orion never sends an email directly. It delegates
  all real-world work to **OpenClaw**, a separate local daemon.
- **Not cloud-dependent.** STT, TTS, the LLM and (with `orion up --offline`)
  the LiveKit transport can all run locally and free.

---

## 2. The core idea: two brains, one gate

This is the single most important thing to understand, and it is not obvious
from the file layout.

**There are two independent decision-makers in this system:**

| | Brain A — the voice LLM | Brain B — the `LLMPlanner` |
|---|---|---|
| Lives in | the LiveKit voice pipeline | `orion/core/planner.py` |
| Decides by | native function-calling over MCP tools | asking an LLM for a JSON plan |
| Triggered by | the user speaking | `POST /api/tasks`, scheduler jobs, dev CLI |
| Produces | one tool call at a time | a multi-step `TaskPlan` |

They never run in the same request. Voice input uses Brain A; dashboard and
scheduled input use Brain B. Both choose from the **same tool registry** and
funnel every call into the same `ExecutionEngine`, and therefore the same
approval gate.

```mermaid
flowchart TD
    V["🎤 Voice input"] --> A["Brain A<br/>voice LLM · function calling"]
    D["🖥️ Dashboard POST /api/tasks"] --> B["Brain B<br/>LLMPlanner · JSON plan"]
    S["⏰ Scheduler job"] --> B

    A -->|every tool call| E["ExecutionEngine"]
    B --> E

    E --> G{"Approval gate<br/>safety level?"}
    G -->|READ_ONLY / LOW_RISK| OC["OpenClaw daemon"]
    G -->|EXTERNAL_SIDE_EFFECT<br/>DESTRUCTIVE| W["⏸ AWAITING_APPROVAL"]
    W -->|human approves| OC

    OC --> R["Result"]
```

**The gate is the invariant.** No matter which brain decided, a risky tool call
stops and waits for a human.

---

## 3. Runtime topology

Orion runs as **one app** (`orion up`) next to the OpenClaw daemon, plus
optional local model servers.

| Process | Start with | Port | Owns |
|---|---|---|---|
| OpenClaw gateway | `openclaw gateway --port 18789` | 18789 | All real-world execution |
| **Orion app** | `make up` / `orion up` | 8000 | Engine, API (`/api`), MCP tools (`/mcp/sse`), scheduler, dashboard (`/`) |
| ↳ Voice agent | child of `orion up` | — | Mic/speaker, voice LLM |
| ↳ LiveKit server | child of `orion up --offline` (or already running) | 7880 | Local audio transport instead of LiveKit Cloud |

The voice agent is still its own OS process, because LiveKit's worker model
requires one, but `orion up` starts and stops it; `--no-voice` skips it. It
holds no engine: it reaches the tools over `/mcp/sse` like any MCP client.
During dashboard development, `make dashboard` runs Vite on 5173 and proxies
`/api` to the app.

Optional free local model servers (see §8, §9):

| Server | Port | Used when |
|---|---|---|
| whisper.cpp | 8080 | `STT_PROVIDER=whisper_local` |
| `orion parakeet-server` | 8090 | `STT_PROVIDER=parakeet_local` (Apple Silicon) |
| kokoro-fastapi | 8880 | `TTS_PROVIDER=kokoro` |
| mlx-audio | 8881 | `TTS_PROVIDER=mlx_audio` (Apple Silicon) |
| Ollama | 11434 | `LLM_PROVIDER=ollama` |

### One runtime per process

Nothing in Orion does work at import time. `create_app()` in `orion/app.py`
calls `build_runtime(config)` **once**, which constructs `store`, `events`,
`registry`, `approval_gate`, `planner` and `engine`, and passes that `Runtime`
to the API routes and to the generated MCP tools (`expose_tools(mcp, runtime)`). The
app's lifespan creates the database (`init_db()`) and starts and stops the
scheduler.

So a task created by voice and approved from the dashboard is created,
paused and resumed by the **same** `ExecutionEngine`, and a test asserts there
is exactly one per app. The dev text agent (`make dev`) and tests build their
own runtime with the same function.

---

## 4. Component map

```
Orion/
├── agent.py               Voice agent — LiveKit worker (Brain A)
│
├── bridge/                → OpenClaw
│   ├── openclaw_client.py Async HTTP client, retries, error→speech
│   └── response_parser.py Strips markdown/JSON so output is TTS-safe
│
├── orion/
│   ├── app.py             The one ASGI app: /api, /mcp, dashboard, lifespan
│   ├── cli.py             `orion up`, `orion openclaw-config`
│   ├── openclaw_setup.py  Least-privilege OpenClaw agents + startup checks
│   ├── offline.py         Offline profile check + local LiveKit server
│   ├── config.py          All env vars, typed; validate() on startup
│   ├── persona.py         Loads system prompt + injects memories
│   ├── prompts/           Orion's character prompt
│   │
│   ├── core/              THE ENGINE
│   │   ├── models.py      Task, TaskStep, ApprovalRequest, safety levels
│   │   ├── engine.py      ExecutionEngine — the task lifecycle
│   │   ├── approvals.py   ApprovalGate + ApprovalStore protocol
│   │   ├── registry.py    ToolDefinition[T] + ToolRegistry
│   │   ├── planner.py     LLMPlanner (Brain B)
│   │   ├── runtime.py     build_runtime(), build_registry()
│   │   ├── store.py       InMemoryTaskStore (reference impl)
│   │   └── events.py      EventRecorder (in-memory)
│   │
│   ├── llm/               PROVIDER REGISTRY
│   │   ├── providers.py   One table: gemini/openai/claude/groq/ollama
│   │   └── client.py      complete_text() — neutral across transports
│   │
│   ├── db/                PERSISTENCE
│   │   ├── models.py      6 SQLModel tables
│   │   ├── session.py     Engine at ~/.orion/orion.db
│   │   ├── task_store.py  PersistentTaskStore
│   │   └── event_store.py PersistentEventStore
│   │
│   ├── tools/             24 tool declarations, 8 domains; _mcp.py generates
│   │                      the voice LLM's MCP surface from the registry;
│   │                      _safe.py: single-line args, quoting, URL schemes
│   ├── evals/             tool-selection eval + latency benchmark
│   ├── services/          memory · conversation · scheduler · outcomes
│   ├── voice_outcomes.py  Speaks approval outcomes in the voice session
│   └── api/               FastAPI routes; security.py: install token, Host check
│
├── dashboard/             Vite + React + TS operator UI
├── dev/                   Mock OpenClaw · text agent · DB seeder
└── tests/                 132 tests
```

---

## 5. Request flows

This section traces every way work enters the system.

### 5.1 Voice, read-only path

**"Orion, check my email."**

```mermaid
sequenceDiagram
    participant U as User
    participant LK as Voice agent
    participant MCP as /mcp (generated tools)
    participant E as ExecutionEngine
    participant OC as OpenClaw
    U->>LK: speech
    LK->>LK: Silero VAD segments utterance
    LK->>LK: STT → text
    LK->>LK: LLM picks tool check_email
    LK->>MCP: call check_email(count=10, filter="unread")
    MCP->>E: Runtime.run_tool("check_email", …)
    E->>E: task + events · READ_ONLY passes the gate
    E->>OC: POST /v1/chat/completions<br/>"Check my unread emails…"
    OC-->>E: raw markdown result
    E->>E: clean_for_tts() strips markdown/JSON
    E-->>MCP: Task(SUCCEEDED)
    MCP-->>LK: plain string
    LK->>LK: TTS (sentence-chunked)
    LK-->>U: speech
```

Step by step:

1. **Mic → VAD.** Silero VAD detects speech boundaries. Whisper is a batch model,
   so LiveKit uses VAD to slice a complete utterance before transcribing.
2. **STT.** `_build_stt()` in `agent.py` returns the configured provider.
3. **LLM.** The voice LLM has the 24 MCP tools in its context and picks one.
4. **MCP call.** The MCP tool was generated from the `check_email`
   declaration in `orion/tools/email.py`; it calls `Runtime.run_tool()`.
5. **Through the engine.** The engine records a task and its events. The tool
   is `READ_ONLY`, so the gate lets it straight through and its handler sends
   the instruction to OpenClaw. Nothing pauses, but the call is audited.
6. **Cleaning.** `clean_for_tts()` removes markdown, code blocks, URLs, JSON, and
   truncates to 800 characters at a sentence boundary.
7. **TTS.** Non-streaming engines are auto-wrapped by LiveKit in a
   `tts.StreamAdapter` with a sentence tokenizer, so audio starts after the
   first sentence.

**Tools on this path** (`READ_ONLY` / `LOW_RISK`): `check_email`,
`summarize_inbox`, `get_events`, `read_file`, `search_files`, `search_web`,
`take_screenshot`, `get_time`, `get_system_info`, `what_do_i_know_about`,
`open_editor`, `open_url`, `remember_this`, `forget`.

---

### 5.2 Voice, side-effect path — where the gate engages

**"Orion, email Priya that I'll be late."**

```mermaid
sequenceDiagram
    participant U as User
    participant LK as Voice agent
    participant T as /mcp (generated tools)
    participant E as ExecutionEngine
    participant G as ApprovalGate
    participant DB as SQLite
    participant API as Dashboard
    participant OC as OpenClaw

    U->>LK: "email Priya…"
    LK->>T: send_email(to, subject, body)
    T->>E: Runtime.run_tool("send_email", …)
    E->>DB: create task + step
    E->>E: step → RUNNING
    E->>G: tool requires approval?
    G->>DB: ApprovalRequest
    E->>DB: task → AWAITING_APPROVAL
    E-->>T: Task(AWAITING_APPROVAL)
    T-->>LK: "The email is waiting for your approval…"
    LK-->>U: spoken notice
    Note over U,API: — human switches to dashboard —
    API->>E: POST /api/tasks/{id}/approve
    E->>G: grant_latest_for_task()
    E->>E: replay steps, skip SUCCEEDED
    E->>OC: send the email
    OC-->>E: result
    E->>DB: task → SUCCEEDED
```

The path is identical to 5.1 up to the gate: every generated MCP tool calls
`Runtime.run_tool()`, which builds a **one-step plan** and hands it to
`engine.create_task_with_steps()`, so **Brain B (the planner) is skipped**. The
voice LLM already decided; the engine executes under the gate. The only
difference is the safety level: here the gate pauses the task.
`describe_outcome()` in `orion/tools/_mcp.py` turns the task into one spoken
sentence, so a failure can never be reported as success.

**Tools on this path** (`EXTERNAL_SIDE_EFFECT` / `DESTRUCTIVE`): `send_email`,
`send_whatsapp`, `send_telegram`, `send_slack`, `create_event`,
`reschedule_event`, `create_project`, `run_code`, `write_file`, `run_command`.

The voice turn **ends** at "waiting for your approval". When you later approve
or reject in the dashboard, the voice session hears about it:

```mermaid
sequenceDiagram
    participant D as Dashboard
    participant E as ExecutionEngine
    participant ES as Event store
    participant API as /api/events/outcomes (SSE)
    participant V as Voice agent
    V->>API: subscribe at session start
    D->>E: POST /api/tasks/{id}/approve (+ token)
    E->>ES: task_succeeded
    ES->>API: subscriber callback → outcome_for()
    API-->>V: {"speech": "The WhatsApp message you approved went through. …"}
    V->>V: wait until neither side is speaking
    V-->>V: session.say(speech)
```

`orion/services/outcomes.py` words the update from the tool's declaration
(approved and done, approved but failed, or rejected); only tasks that went
through approval are announced. `orion/voice_outcomes.py` is the listener;
`dev/listen_outcomes.py` prints the same announcements in a terminal.

---

### 5.3 Dashboard / scheduler path — where the planner runs

**`POST /tasks {"user_intent": "check email and reply to Priya"}`**

```mermaid
sequenceDiagram
    participant C as Dashboard / Scheduler
    participant E as ExecutionEngine
    participant P as LLMPlanner
    participant LLM as Provider
    participant R as ToolRegistry
    participant G as ApprovalGate

    C->>E: create_task(user_intent)
    E->>E: task → PLANNING
    E->>P: plan(intent)
    P->>R: list_tools() → build prompt
    P->>LLM: complete_text(system, user)
    LLM-->>P: JSON plan
    P->>P: strip fences, parse, validate tools
    P-->>E: TaskPlan(steps)
    E->>E: append steps, task → RUNNING
    loop each step
        E->>G: requires approval?
        alt risky
            G-->>E: halt → AWAITING_APPROVAL
        else safe
            E->>E: execute, record events
        end
    end
```

The planner is **defensive by design**. Any of these fall back to a safe
single-step `echo_tool` plan rather than crashing:

- no API key for the provider (`LLMUnavailable`)
- unknown provider name (`ValueError`)
- network failure
- unparseable JSON
- a plan referencing a tool not in the registry
- an empty step list

This is why `ExecutionEngine` can call `_plan()` without a try/except.

---

### 5.4 Memory path

Memory tools (`remember_this`, `what_do_i_know_about`, `forget`) are declared
in `orion/tools/memory.py` like every other tool, so voice and the planner use
the same three, through the engine. Their handlers call `MemoryService`
directly rather than OpenClaw.

`remember_this` first extracts a `{key, value}` pair from natural language:

1. In dev mode → `_heuristic_extract()` (regex: `"my X is Y"`, `"X: Y"`, slugify).
2. Otherwise → an LLM call via `complete_text()`, falling back to the heuristic
   on any failure.

Stored memories are injected into the **system prompt at session start** by
`orion/persona.py`, so Orion "remembers" across sessions.

---

### 5.5 Conversation logging

`agent.py` attaches two LiveKit hooks:

- `user_input_transcribed` → logs `role="user"`
- `agent_speech_committed` → logs `role="assistant"`

Both write to the `conversation_log` table via `ConversationLogger`, keyed by
`ctx.room.name` as the session ID. The whole block is wrapped in try/except —
logging failures never break the voice session.

---

## 6. The approval gate

### Safety levels

Defined in `orion/core/models.py`:

| Level | Approval? | Meaning |
|---|---|---|
| `READ_ONLY` | no | Cannot change anything |
| `LOW_RISK` | no | Local, reversible |
| `EXTERNAL_SIDE_EFFECT` | **yes** | Visible to other people |
| `DESTRUCTIVE` | **yes** | Can destroy data or run arbitrary code |

`ToolDefinition.requires_approval` is simply membership in the bottom two.

### Current assignments

Every voice tool's level is pinned in `EXPECTED_SAFETY` in
`tests/test_tool_surface.py`, so adding a tool or changing a level is a
reviewed change.

| Level | Tools |
|---|---|
| READ_ONLY | `check_email`, `summarize_inbox`, `get_events`, `read_file`, `search_files`, `search_web`, `take_screenshot`, `get_time`, `get_system_info`, `what_do_i_know_about` |
| LOW_RISK | `open_editor`, `open_url`, `remember_this`, `forget` |
| EXTERNAL_SIDE_EFFECT | `send_email`, `send_whatsapp`, `send_telegram`, `send_slack`, `create_event`, `reschedule_event` |
| DESTRUCTIVE | `create_project` (installs dependencies, which runs third-party code), `run_code`, `write_file`, `run_command` |

The engine also registers two internal fallbacks that are never exposed to
voice: `echo_tool` (READ_ONLY) and `mock_send_email` (EXTERNAL_SIDE_EFFECT).

### Task state machine

```mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> PLANNING
    PLANNING --> RUNNING
    RUNNING --> AWAITING_APPROVAL: risky step
    AWAITING_APPROVAL --> RUNNING: approved
    AWAITING_APPROVAL --> FAILED: rejected (step SKIPPED)
    RUNNING --> SUCCEEDED
    RUNNING --> FAILED: tool raised
    SUCCEEDED --> [*]
    FAILED --> [*]
```

### How resumption works

`_run()` is **idempotent and replayable**. On resume it iterates all steps and
`continue`s past any already `SUCCEEDED`. So approving a task re-enters the same
loop and picks up exactly where it halted. `_can_execute_risky_step()` scans
approvals in reverse for a granted record matching that step.

### Event log

Eleven event types are written to the `events` table:

`task_created` · `task_started` · `task_succeeded` · `task_failed` ·
`task_rejected` · `step_started` · `tool_started` · `tool_succeeded` ·
`tool_failed` · `approval_required` · `approval_granted`

This is the audit trail. `GET /tasks/{id}/events` returns it; `GET
/tasks/{id}/stream` pushes it over SSE, polling every 0.5s and closing when the
task reaches a terminal state.

---

## 7. Data model and persistence

SQLite at `~/.orion/orion.db`, six tables via SQLModel:

| Table | Holds |
|---|---|
| `tasks` | id, user_intent, status, error, timestamps |
| `task_steps` | step state; nested objects JSON-encoded into columns |
| `approvals` | task_id, step_id, tool_name, reason, approved_at/by |
| `events` | append-only audit log; payload as JSON |
| `memories` | key/value facts, upserted by normalised key |
| `conversation_log` | session_id, role, content, timestamp |

### Two model layers

There are **two parallel model definitions**, and you need both:

- `orion/core/models.py` — Pydantic. What the engine and API speak.
- `orion/db/models.py` — SQLModel tables. Flat, SQLite-friendly.

All timestamp columns use `UTCDateTime` (`orion/db/models.py`): SQLite has no
timezone support, so values are stored as naive UTC and handed back tz-aware.

`task_store.py` hand-converts between them (`_step_to_record`,
`_record_to_step`), JSON-stringifying nested fields like `tool_call` and
`planned_tool_args`. See §12 — this is duplication worth removing.

`InMemoryTaskStore` and `EventRecorder` still exist as reference
implementations and satisfy the same interface, but production uses the
persistent versions.

---

## 8. The LLM layer

**One registry, three consumers.** `orion/llm/providers.py` is the single source
of truth; the voice agent, the planner, and memory extraction all resolve from
it.

| Provider | Alias | Transport | Key | Free? |
|---|---|---|---|---|
| `gemini` | `google` | OpenAI-compat | `GOOGLE_API_KEY` | free tier |
| `openai` | `chatgpt` | OpenAI-compat | `OPENAI_API_KEY` | no |
| `claude` | `anthropic` | **Anthropic SDK** | `ANTHROPIC_API_KEY` | no |
| `groq` | — | OpenAI-compat | `GROQ_API_KEY` | free tier |
| `ollama` | `local` | OpenAI-compat | none | **yes, local** |

Switching is one env var: `LLM_PROVIDER=claude`. Override the model with
`ORION_LLM_MODEL=claude-opus-5`.

### Why two transports

Gemini, OpenAI, Groq and Ollama genuinely expose OpenAI-compatible
`/chat/completions`, so they share one HTTP path with a different `base_url` and
one LiveKit plugin.

**Claude deliberately does not use an OpenAI-compatibility shim.** It uses the
official `anthropic` SDK and the native `livekit-plugins-anthropic` plugin,
because the Messages API is the supported path for tool use. Two concrete
differences the registry encodes:

- `system` is a **top-level parameter**, not a message with `role: "system"`.
- Anthropic models **reject `temperature`** and return HTTP 400. `ProviderSpec`
  carries `supports_temperature=False`, and `client.py` omits the field.

`ProviderSpec` also distinguishes `model` (conversational, used by voice) from
`utility_model` (cheaper, used for planning and memory extraction).

---

## 9. The speech layer

Providers are selected by string in `agent.py`'s `_build_stt()` / `_build_tts()`.

**STT:** `whisper_local` (free, local) · `parakeet_local` (free, local) ·
`groq` · `whisper` · `sarvam` · `deepgram`
**TTS:** `kokoro` (free, local) · `mlx_audio` (free, local) · `elevenlabs` ·
`openai` · `sarvam`

All local options are **OpenAI-compatible HTTP servers you run yourself**, so
the voice agent needs no extra Python dependencies; the existing `openai`
plugin just points at localhost.

### Parakeet: Orion's own STT server

`parakeet-mlx` has no HTTP server, so `orion/speech/parakeet_server.py` wraps
it in the one endpoint LiveKit's STT plugin calls (`POST
/v1/audio/transcriptions`, multipart). The transcriber is injected, so the
request/response contract is tested in CI without MLX. LiveKit always sends
16-bit PCM WAV, which `decode_wav()` decodes and resamples with numpy, so the
model gets samples directly and **ffmpeg isn't needed**; other formats fall
back to parakeet-mlx's own (ffmpeg-based) loader. It's an optional extra
(`uv sync --extra parakeet`), installed only on Apple Silicon.

Parakeet v3 is faster than Whisper and more accurate for English, but covers
only English and ~25 European languages; `whisper_local` remains the default
for its ~100.

`mlx_audio` requests WAV from the server because mlx-audio needs ffmpeg for
the plugin's default MP3.

### Non-streaming is handled for you

Whisper, Parakeet and Kokoro are batch models. LiveKit 1.6.0 auto-wraps them:

- non-streaming **STT** → `stt.StreamAdapter(stt, vad)` — VAD segments the audio
- non-streaming **TTS** → `tts.StreamAdapter(tts, sentence_tokenizer)` —
  playback begins after the first sentence rather than the full response

`_endpointing_delay()` tunes silence-before-transcribe per provider (0.07s for
Sarvam's streaming STT up to 0.3s for batch Whisper).

**A fully free stack** is `LLM_PROVIDER=ollama` + `STT_PROVIDER=whisper_local`
(or `parakeet_local`) + `TTS_PROVIDER=kokoro` (or `mlx_audio`). It validates with
zero API keys, LiveKit transport aside. The README has a memory budget for a
16 GB Mac.

---

## 10. The dashboard

Vite + React + TypeScript. `orion up` serves the built dashboard at `/` and
the API at `/api` on the same origin. `make dashboard` runs the Vite dev server
on 5173 with hot reload and proxies `/api` to the app.

| Component | Shows |
|---|---|
| `StatusBar` | health, OpenClaw reachability, active providers |
| `TaskList` | all tasks with status |
| `TaskDetail` | steps, tool args, results |
| `ApprovalPanel` | pending approvals with Approve / Reject |
| `ConversationLog` | recent voice exchanges |
| `VoicePanel` | **Talk**: joins the voice room from the browser (token from `/api/voice/token`; `livekit-client` lazy-loaded) |
| `SchedulerPanel` | jobs and next run times |

`hooks/useOrion.ts` uses plain `setInterval` polling — tasks every 2s, health and
scheduler every 5s, conversations every 3s. An SSE helper (`streamEvents`)
exists in `api/orion.ts` but the components currently poll.

**The dashboard is the approval UI.** Without it (or a raw `POST
/api/tasks/{id}/approve`), gated tasks sit in `AWAITING_APPROVAL` forever.

State-changing API routes (create, approve, reject) require the per-install
token in the `X-Orion-Token` header; the dashboard fetches it once from
`/api/auth/token`. Every request must also carry a loopback `Host` header. Both
defend against other websites in your browser (CSRF, DNS rebinding); see
[SECURITY.md](SECURITY.md).

---

## 11. Development environment

You can do most work with **no API keys and no OpenClaw**:

```bash
make setup    # deps + .env
make dev      # text agent against mock OpenClaw
```

| Tool | Purpose |
|---|---|
| `dev/mock_openclaw.py` | Fake OpenClaw on :18789; keyword-matched replies; also serves mock JSON *plans* so the planner works offline |
| `dev/text_agent.py` | Terminal Orion — full engine, no voice. Commands: `tasks`, `events`, `memory`, `health`, `exit`; prompts interactively on approval |
| `dev/seed_db.py` | Realistic fake tasks for dashboard work |
| `orion eval` / `make eval` | Tool-selection accuracy (51 cases, incl. prompt injection) for any LLM provider |
| `orion bench` / `make bench` | Per-stage STT / LLM / TTS latency and memory on this machine |

`config.validate()` returns immediately when `DEV_MODE=true`, so nothing
demands credentials.

```bash
make test     # 132 tests
make lint     # ruff + mypy, both clean
```

Tests use an in-memory SQLite (`tests/conftest.py` swaps `db_session.engine`) and
shim `dotenv`, so they never touch `~/.orion/orion.db`.

---

## 12. Known rough edges

Honest list. These are design debts, not mysteries — don't spend a day thinking
you broke them.

1. **The planner never runs on the voice path.** `LLMPlanner` is the most
   sophisticated component (~230 lines) but voice tools call
   `create_task_with_steps()`, which takes explicit steps. Brain B only serves
   the dashboard, the scheduler and the dev CLI. Decide which brain owns
   planning; having both is the worst option.

2. ✅ **Resolved (#16).** A capability used to be defined two or three times
   (MCP wrapper, registry entry, runtime wrapper). Each is now one
   `ToolDefinition` in `orion/tools/`; the MCP surface is generated from it.

3. ✅ **Resolved (#16).** Read-only tools used to bypass the engine, and nothing
   stopped a new tool from skipping the gate. Every MCP tool is now generated
   from the registry and runs through the engine; tests check that each one
   creates a task and that every tool's safety level matches a reviewed table.

4. ✅ **Resolved (#18).** The voice session used to never learn an approval's
   outcome. It now subscribes to `/api/events/outcomes` and says what happened
   at the next pause (§5.2). Approval itself deliberately stays out of voice's
   reach: a voice "approve" tool would let the LLM that proposed an action
   (possibly steered by an email it just read) approve it too.

5. ✅ **Resolved (#15).** `GET /api/scheduler/jobs` used to spin up a throwaway
   scheduler because the real one lived in another process. It now reads the
   live `OrionScheduler` running in the app's lifespan.

6. ✅ **Resolved (#15).** Orion used to be four processes sharing one SQLite
   file, each with its own engine. It is now one app with one engine; only the
   voice agent is a separate (supervised) process, and it holds no engine.

7. **Two model layers with hand-written converters.** ~150 lines of
   serialization glue in `task_store.py`, in a library (SQLModel) whose whole
   premise is being both Pydantic and SQL at once.

8. ✅ **Resolved (#15).** Importing `orion.core.runtime` used to create the DB
   and build singletons. Nothing runs at import time now (a test checks this);
   `build_runtime()` and the app lifespan do the work.

9. ✅ **Resolved (#14).** GitHub Actions runs ruff, mypy, pytest and the
   dashboard build on every PR; `main` requires both checks.

10. **Coverage is uneven.** The planner, LLM registry, runtime adapters,
    scheduler, rejection/failure paths, gate coverage and timestamp handling are
    tested (`tests/test_engine.py`), as are the single-process app, a real
    MCP-over-SSE round trip (`tests/test_app.py`) and the generated tool surface
    (`tests/test_tool_surface.py`). Most API routes and the task SSE stream are
    not.

11. ⚠️ **Partly resolved (#17).** The gate only governs what Orion *asks* for:
    every tool sends a natural-language instruction to OpenClaw, an agent with
    broad access. OpenClaw can't restrict tools per request, so Orion now
    (a) rejects multi-line and over-long text in single-line arguments,
    (b) sends every value as a quoted literal that OpenClaw is told is data, and
    (c) with `ORION_OPENCLAW_SCOPED_AGENTS=true`, runs each call on a
    least-privilege OpenClaw agent for its safety level (`orion-reader` can't
    exec or write). What remains: scoping depends on the user configuring those
    agents, and a malicious OpenClaw skill is out of Orion's reach. See
    [SECURITY.md](SECURITY.md).

---

## 13. How to add things

### Add a tool

Every tool, read-only or not, is one declaration in `orion/tools/`. Pick the
module for its domain (or create one and add it to `all_tools()` in
`orion/tools/__init__.py`):

```python
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

That's all the wiring. The voice LLM sees `play_music` with typed, described
arguments; the planner can plan it; every call is a task in the audit log; and
if you choose `EXTERNAL_SIDE_EFFECT` or `DESTRUCTIVE`, it waits for approval.
For a tool that doesn't use OpenClaw, build a `ToolDefinition` with your own
handler returning `{"message": "..."}` (see `get_time`).

Then:

1. Add it to `EXPECTED_SAFETY` in `tests/test_tool_surface.py`. The test fails
   until you do, so the safety level is a deliberate choice.
2. Add a mock response in `dev/mock_openclaw.py`.
3. Restart Orion (`make up`).

### Add an LLM provider

Add one `ProviderSpec` to `PROVIDERS` in `orion/llm/providers.py`. If it is
OpenAI-compatible, nothing else changes — the voice agent, planner and memory
extraction all pick it up. Only a genuinely different API (like Anthropic's)
needs a new branch in `client.py` and `_build_llm()`.

### Add a speech provider

Add a branch to `_build_stt()` / `_build_tts()` in `agent.py`. Providers needing
no key require no config change — `validate()` skips unknown names.

### Conventions

Commits are `<type>(<scope>): <description>` with types `feat`, `fix`,
`refactor`, `test`, `docs`, `chore`, `ci`. Run `make test` and `make lint`
before opening a PR. See [CONTRIBUTING.md](CONTRIBUTING.md).
