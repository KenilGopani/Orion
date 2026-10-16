"""
Least-privilege OpenClaw setup and startup safety checks.

OpenClaw can't restrict an agent's tools per request: a chat-completions call
only chooses *which agent* runs it (``"model": "openclaw/<agentId>"``). Tools,
exec mode and sandboxing are configured per agent in ``~/.openclaw/openclaw.json``.

So Orion maps each tool's safety level to a restricted agent. With
``ORION_OPENCLAW_SCOPED_AGENTS=true``:

- READ_ONLY tools run on ``orion-reader``, which cannot exec, write or spawn
  sessions. A prompt injection inside an email the reader just fetched has no
  dangerous tool to call.
- LOW_RISK and EXTERNAL_SIDE_EFFECT tools (sends, invites — human-approved)
  run on ``orion-actor``, which still cannot exec or write files.
- DESTRUCTIVE tools (commands, code, file writes — human-approved) run on
  ``orion-exec``.

``orion openclaw-config`` prints the agent definitions to paste in.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import json5

from orion.config import Config
from orion.core.models import ToolSafetyLevel

logger = logging.getLogger("orion.openclaw")

OPENCLAW_CONFIG_PATH = Path.home() / ".openclaw" / "openclaw.json"

AGENT_FOR_LEVEL: dict[ToolSafetyLevel, str] = {
    ToolSafetyLevel.READ_ONLY: "orion-reader",
    ToolSafetyLevel.LOW_RISK: "orion-actor",
    ToolSafetyLevel.EXTERNAL_SIDE_EFFECT: "orion-actor",
    ToolSafetyLevel.DESTRUCTIVE: "orion-exec",
}

# Tools OpenClaw's security docs recommend denying to agents that handle
# untrusted content, plus file mutation and process control.
_NO_CONTROL_PLANE = ["gateway", "cron", "sessions_spawn", "sessions_send"]
_NO_MUTATION = ["exec", "process", "write", "edit", "apply_patch"]

AGENT_DEFINITIONS: dict[str, dict[str, Any]] = {
    "orion-reader": {
        "tools": {"deny": _NO_MUTATION + _NO_CONTROL_PLANE, "exec": {"mode": "deny"}},
    },
    "orion-actor": {
        "tools": {"deny": _NO_MUTATION + _NO_CONTROL_PLANE, "exec": {"mode": "deny"}},
    },
    "orion-exec": {
        # Every call reaching this agent was approved by a human in Orion, so it
        # may run the approved command; an OpenClaw allowlist would refuse it.
        "tools": {"deny": _NO_CONTROL_PLANE, "exec": {"mode": "full"}},
    },
}


def agent_for(level: ToolSafetyLevel, cfg: Config) -> str | None:
    """The OpenClaw agent a tool at ``level`` should run on, or None for the default."""
    return AGENT_FOR_LEVEL[level] if cfg.openclaw_scoped_agents else None


def config_snippet() -> str:
    """The ``agents.entries`` block that defines Orion's restricted agents."""
    body = json.dumps({"agents": {"entries": AGENT_DEFINITIONS}}, indent=2)
    return (
        "// Orion's least-privilege agents: merge into ~/.openclaw/openclaw.json,\n"
        "// add the skills each agent needs (e.g. \"skills\": [\"gmail\"]), and deny\n"
        "// any messaging/email *send* tools on orion-reader by name. If Docker is\n"
        "// available, also consider \"sandbox\": {\"mode\": \"all\"} for orion-reader.\n"
        "// Then set ORION_OPENCLAW_SCOPED_AGENTS=true in Orion's .env.\n"
        f"{body}\n"
    )


def _get(data: dict[str, Any], dotted: str) -> Any:
    node: Any = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def check_openclaw_config(cfg: Config, path: Path = OPENCLAW_CONFIG_PATH) -> list[str]:
    """Warnings about an unsafe or incomplete OpenClaw configuration."""
    if not path.exists():
        return [f"No OpenClaw config at {path}; can't verify its safety settings."]
    try:
        data = json5.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"Couldn't parse {path} ({exc}); can't verify its safety settings."]

    warnings: list[str] = []
    bind = _get(data, "gateway.bind") or "loopback"
    if bind != "loopback":
        warnings.append(
            f'gateway.bind is "{bind}": the gateway is reachable beyond this machine. '
            'Use "loopback" unless you need remote access.'
        )
    if _get(data, "gateway.auth.mode") == "none":
        warnings.append("gateway.auth.mode is \"none\": anything that can reach the gateway controls it.")

    exec_mode = _get(data, "tools.exec.mode") or _get(data, "tools.exec.security") or "full"
    if exec_mode == "full":
        warnings.append(
            "tools.exec.mode is \"full\" (OpenClaw's default): the default agent runs shell "
            'commands without asking. Prefer "allowlist" or "ask", and enable scoped agents.'
        )

    entries = _get(data, "agents.entries") or {}
    if cfg.openclaw_scoped_agents:
        missing = [name for name in AGENT_DEFINITIONS if name not in entries]
        if missing:
            warnings.append(
                f"ORION_OPENCLAW_SCOPED_AGENTS is on but OpenClaw has no {', '.join(missing)} "
                "agent(s); those tools will fail. Run `orion openclaw-config` for the definitions."
            )
    else:
        warnings.append(
            "Scoped agents are off: every tool, read-only ones included, runs on OpenClaw's "
            "default agent with all its tools. Run `orion openclaw-config` to set them up."
        )
    return warnings


def log_openclaw_safety(cfg: Config, path: Path = OPENCLAW_CONFIG_PATH) -> None:
    for warning in check_openclaw_config(cfg, path):
        logger.warning("OpenClaw safety: %s", warning)
