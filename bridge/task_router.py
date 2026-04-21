"""
Task Router
============
Classifies user intent into categories for logging and metrics.

The LLM handles actual tool selection via function calling — this module
provides a lightweight keyword-based classifier for observability.
"""

from __future__ import annotations

INTENT_CATEGORIES: dict[str, list[str]] = {
    "email": [
        "check email", "send email", "read inbox", "reply to",
        "email", "inbox", "unread", "mail", "compose",
    ],
    "messaging": [
        "message", "whatsapp", "text", "telegram", "slack",
        "send a message", "dm", "chat",
    ],
    "calendar": [
        "schedule", "calendar", "meeting", "remind me", "what's on",
        "appointment", "event", "reschedule", "cancel meeting",
    ],
    "code": [
        "create project", "write code", "run script", "open vs code",
        "code", "python", "javascript", "compile", "debug", "project",
    ],
    "files": [
        "open file", "read file", "find file", "save", "write file",
        "search files", "directory", "folder",
    ],
    "browser": [
        "open", "search", "google", "browse", "website",
        "url", "screenshot", "web page",
    ],
    "system": [
        "what time", "system info", "shutdown", "restart",
        "battery", "disk space", "uptime", "run command",
    ],
    "memory": [
        "remember", "what do you know about", "forget",
        "recall", "noted", "keep in mind",
    ],
    "direct": [],  # Simple Q&A — handled by LLM directly, no OpenClaw
}


def classify_intent(text: str) -> str:
    """
    Return the best-matching intent category for a given user utterance.

    Parameters
    ----------
    text : str
        Raw transcribed user speech.

    Returns
    -------
    str
        One of the keys in ``INTENT_CATEGORIES``, or ``"direct"``
        if no keyword match is found.
    """
    lower = text.lower()
    for category, keywords in INTENT_CATEGORIES.items():
        if category == "direct":
            continue
        for keyword in keywords:
            if keyword in lower:
                return category
    return "direct"
