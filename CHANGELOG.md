# Changelog

All notable changes to Orion are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and Orion uses
[Semantic Versioning](https://semver.org/).

## [1.0.0] — Unreleased

The first release: a private voice agent that never sends, runs or posts
anything without your approval, and can run entirely on your own machine.

### Added

- **One command to run everything.** `orion up` serves the dashboard, the REST
  API, the voice agent's MCP tools and the scheduler from one process with one
  engine, and supervises the voice agent. ([#24](https://github.com/KenilGopani/Orion/pull/24))
- **Spoken approval outcomes.** After you approve or reject an action in the
  dashboard, the voice session says what happened at the next pause.
  ([#27](https://github.com/KenilGopani/Orion/pull/27))
- **Least-privilege OpenClaw agents.** Read-only tools run on an OpenClaw agent
  that can't exec or write; `orion openclaw-config` prints the definitions and
  checks your OpenClaw config. ([#26](https://github.com/KenilGopani/Orion/pull/26))
- **`SECURITY.md`**: threat model, trust boundaries, an attacks-and-mitigations
  table, and a hardening checklist. ([#26](https://github.com/KenilGopani/Orion/pull/26))
- **Local Parakeet speech-to-text** via `orion parakeet-server` (Apple Silicon,
  no ffmpeg needed), and **mlx-audio** text-to-speech.
  ([#28](https://github.com/KenilGopani/Orion/pull/28))
- **Evals and benchmarks.** `orion eval` measures tool-selection accuracy and
  prompt-injection resistance over 51 cases for any LLM provider; `orion bench`
  measures per-stage latency and memory. ([#29](https://github.com/KenilGopani/Orion/pull/29))
- **Offline mode.** `orion up --offline` checks every component is local and
  runs a loopback-only LiveKit server, so nothing leaves the machine.
  ([#30](https://github.com/KenilGopani/Orion/pull/30))
- **Talk panel.** Talk to Orion from the dashboard; no hosted playground needed.
  ([#30](https://github.com/KenilGopani/Orion/pull/30))
- Provider registry for Gemini, OpenAI, Claude (native Anthropic SDK), Groq and
  Ollama, with free local speech defaults. ([#23](https://github.com/KenilGopani/Orion/pull/23))
- CI on every pull request (ruff, mypy, pytest, dashboard build) with locked
  dependencies; `main` requires it. ([#23](https://github.com/KenilGopani/Orion/pull/23))

### Changed

- **Every voice tool is generated from one declaration** in the tool registry,
  and every call, read-only included, goes through the engine and is audited.
  ([#25](https://github.com/KenilGopani/Orion/pull/25))
- The planner sees the same tools as voice, so scheduled jobs such as the
  morning briefing can read email and calendar. ([#25](https://github.com/KenilGopani/Orion/pull/25))
- Tools take their voice names (`send_email`, not `openclaw_send_email`).
  ([#25](https://github.com/KenilGopani/Orion/pull/25))
- The local Ollama default is `qwen3.5:4b`. ([#28](https://github.com/KenilGopani/Orion/pull/28))
- The API lives under `/api` on the same port as everything else;
  `ORION_PORT` replaces `MCP_SERVER_PORT` (still honoured).
  ([#24](https://github.com/KenilGopani/Orion/pull/24))

### Security

- `run_code`, `create_event`, `reschedule_event` and `create_project` now
  require approval; `run_code` previously ran arbitrary code ungated.
  ([#23](https://github.com/KenilGopani/Orion/pull/23), [#25](https://github.com/KenilGopani/Orion/pull/25))
- Approve, reject and create require a per-install token, and every request
  must carry a loopback `Host` header, defeating CSRF and DNS rebinding.
  ([#26](https://github.com/KenilGopani/Orion/pull/26))
- Tool arguments are single-line and length-capped where they should be,
  rendered as quoted data for OpenClaw, and `open_url` accepts only http(s).
  ([#26](https://github.com/KenilGopani/Orion/pull/26))

### Fixed

- A failed file write or shell command was spoken as success.
- Rejecting a task left its approval pending and its step stuck.
- A task naming an unknown tool stayed `RUNNING` forever.
- Timestamps lost their timezone, so the dashboard showed shifted times.
- The dashboard reported HTTP errors as successful approvals.
- `forget` could delete an arbitrary memory on a vague topic.
- The MCP server's startup health check bound the OpenClaw client to a dead
  event loop. ([#23](https://github.com/KenilGopani/Orion/pull/23))

### Removed

- `server.py` and the separate API process (`make server`, `make api`), replaced
  by `orion up`. ([#24](https://github.com/KenilGopani/Orion/pull/24))

[1.0.0]: https://github.com/KenilGopani/Orion/releases/tag/v1.0.0
