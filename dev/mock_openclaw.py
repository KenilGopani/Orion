"""
Mock OpenClaw Server
====================
A lightweight FastAPI server that mimics OpenClaw's OpenAI-compatible API
but returns realistic hardcoded responses. Allows any developer to run
Orion without the real OpenClaw daemon or any API keys.

Run:
    uv run python dev/mock_openclaw.py

Starts on port 18789 — the same port as the real OpenClaw gateway.
"""

from __future__ import annotations

import random
import re
from datetime import datetime

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Mock OpenClaw", version="0.1.0")

# ---------------------------------------------------------------------------
# Mock response templates
# ---------------------------------------------------------------------------

MOCK_RESPONSES: dict[str, str] = {
    "email": (
        "You have 3 unread emails, sir. One from Priya about tomorrow's "
        "deadline marked urgent, one from GitHub with a pull request review, "
        "and a newsletter from Python Weekly."
    ),
    "send email": "Email sent to {recipient} with subject line included, sir.",
    "inbox": (
        "Your inbox summary: 3 unread emails. The most urgent is from Priya "
        "about the project deadline. The other two are a GitHub notification "
        "and a newsletter. Nothing else needs immediate attention."
    ),
    "calendar": (
        "You have 2 meetings today, sir. Standup at 10 AM and design review "
        "at 3 PM. Tomorrow looks clear apart from a one-on-one at 11 AM."
    ),
    "create event": "Calendar event created successfully, sir. '{title}' on {date}.",
    "reschedule": "Event rescheduled successfully, sir.",
    "whatsapp": "Message sent to {recipient} on WhatsApp, sir.",
    "telegram": "Message delivered to {recipient} on Telegram.",
    "slack": "Posted to {channel} on Slack, sir.",
    "read file": (
        "The file contains a Python module with 3 functions and 2 classes. "
        "It appears to be a utility module for data processing."
    ),
    "write file": "File written successfully at '{path}', sir. Content saved.",
    "search files": (
        "Found 5 files matching your query. The most relevant are: "
        "config.py, utils.py, and main.py."
    ),
    "open": "Page opened in your default browser, sir.",
    "search web": (
        "Here are the top results: First, the official documentation covers "
        "your query in detail. Second, a Stack Overflow answer with 150 "
        "upvotes addresses this exact issue."
    ),
    "screenshot": "Screenshot captured. The screen shows your desktop with a terminal window and a browser open.",
    "system info": (
        "You're running macOS on an Apple Silicon chip with 16 GB of RAM. "
        "Disk usage is at 62 percent. System uptime is 3 days."
    ),
    "run command": "Command executed successfully. Exit code 0. Output: operation completed.",
    "remember": "Noted, sir. I'll remember that for future reference.",
    "recall": "Based on what I have stored, here's what I know about that topic.",
    "forget": "Done, sir. That information has been removed from memory.",
    "project": (
        "Project created successfully, sir. Initialized with standard "
        "structure, dependencies, and a starter file."
    ),
    "run code": "Code executed successfully. Output: Hello, World!",
    "editor": "Opened in VS Code, sir.",
}

DEFAULT_RESPONSE = "Task completed, sir."


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str = "openclaw"
    messages: list[ChatMessage]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_after(text: str, keyword: str) -> str | None:
    """Extract the word following a keyword in the text."""
    words = text.split()
    for i, w in enumerate(words):
        if w == keyword and i + 1 < len(words):
            return words[i + 1]
    return None


def _match_response(user_message: str) -> str:
    """Find the best matching mock response for a user message."""
    lower = user_message.lower()

    # Try longest keyword matches first for specificity
    sorted_keys = sorted(MOCK_RESPONSES.keys(), key=len, reverse=True)

    for keyword in sorted_keys:
        if keyword in lower:
            response = MOCK_RESPONSES[keyword]
            # Interpolate placeholders
            response = response.format(
                recipient=_extract_after(lower, "to") or "the contact",
                channel=_extract_after(lower, "channel") or "#general",
                title=_extract_after(lower, "titled") or "Meeting",
                date=_extract_after(lower, "on") or "the scheduled date",
                path=_extract_after(lower, "at") or _extract_after(lower, "file") or "the file",
            )
            return response

    return DEFAULT_RESPONSE


# ---------------------------------------------------------------------------
# Mock planner — returns JSON plans for the LLMPlanner
# ---------------------------------------------------------------------------

# Keyword → (tool_name, default_args)
_TOOL_MAP: dict[str, tuple[str, dict]] = {
    "email": ("openclaw_send_email", {"to": "demo@example.com", "subject": "Orion Task", "body": ""}),
    "send email": ("openclaw_send_email", {"to": "demo@example.com", "subject": "Orion Task", "body": ""}),
    "inbox": ("openclaw_send_email", {"to": "inbox", "subject": "check", "body": "summarise"}),
    "whatsapp": ("openclaw_send_whatsapp", {"recipient": "Priya", "message": ""}),
    "telegram": ("openclaw_send_telegram", {"recipient": "contact", "message": ""}),
    "slack": ("openclaw_send_slack", {"channel": "#general", "message": ""}),
    "calendar": ("openclaw_send_email", {"to": "calendar", "subject": "check", "body": "events today"}),
    "write file": ("openclaw_write_file", {"path": "output.txt", "content": ""}),
    "run command": ("openclaw_run_command", {"command": "echo hello"}),
    "time": ("echo_tool", {"message": ""}),
}

import json as _json


def _mock_plan(user_message: str) -> str:
    """Generate a mock JSON plan based on keywords in the user's intent."""
    lower = user_message.lower()
    steps = []

    # Check for multi-step intents (split on "and", "then", ",")
    parts = re.split(r'\band\b|\bthen\b|,', lower)
    parts = [p.strip() for p in parts if p.strip()]

    for part in parts:
        matched = False
        # Try longest keyword matches first
        for keyword in sorted(_TOOL_MAP.keys(), key=len, reverse=True):
            if keyword in part:
                tool_name, default_args = _TOOL_MAP[keyword]
                args = dict(default_args)
                # Fill in the user's message where appropriate
                if "message" in args and not args["message"]:
                    args["message"] = part.strip()
                if "body" in args and not args["body"]:
                    args["body"] = part.strip()
                if "content" in args and not args["content"]:
                    args["content"] = part.strip()

                steps.append({
                    "name": f"step_{len(steps) + 1}_{keyword.replace(' ', '_')}",
                    "description": f"Execute: {part.strip()}",
                    "tool_name": tool_name,
                    "tool_args": args,
                })
                matched = True
                break

        if not matched:
            # Default to echo for unrecognised parts
            steps.append({
                "name": f"step_{len(steps) + 1}_echo",
                "description": f"Echo: {part.strip()}",
                "tool_name": "echo_tool",
                "tool_args": {"message": part.strip()},
            })

    if not steps:
        steps.append({
            "name": "echo_intent",
            "description": "Echo the user intent",
            "tool_name": "echo_tool",
            "tool_args": {"message": user_message},
        })

    plan = {
        "reasoning": f"Decomposed '{user_message[:60]}' into {len(steps)} step(s)",
        "steps": steps,
    }
    return _json.dumps(plan)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    """OpenAI-compatible chat completions endpoint."""
    user_message = ""
    system_message = ""
    for msg in req.messages:
        if msg.role == "user":
            user_message = msg.content
        if msg.role == "system":
            system_message = msg.content

    # Detect planning requests (from LLMPlanner)
    if "task planning ai" in system_message.lower():
        response_text = _mock_plan(user_message)
    else:
        response_text = _match_response(user_message)

    return {
        "id": f"mock-{random.randint(1000, 9999)}",
        "object": "chat.completion",
        "created": int(datetime.now().timestamp()),
        "model": "mock-openclaw",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response_text,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }


@app.get("/v1/models")
async def list_models():
    """List available models — returns the mock agent."""
    return {
        "object": "list",
        "data": [
            {
                "id": "mock-openclaw",
                "object": "model",
                "created": int(datetime.now().timestamp()),
                "owned_by": "orion-dev",
            }
        ],
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "mode": "mock", "port": 18789}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 55)
    print("  Mock OpenClaw Server")
    print("  Port: 18789 (same as real OpenClaw)")
    print("  Mode: Development — all responses are hardcoded")
    print("=" * 55 + "\n")
    uvicorn.run(app, host="127.0.0.1", port=18789)
