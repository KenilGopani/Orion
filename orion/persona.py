"""
Persona — Orion system prompt loader.

Loads the character prompt template from ``prompts/system_prompt.txt``
and interpolates runtime variables (user name, etc.).
"""

from __future__ import annotations

import os
from pathlib import Path

from orion.config import config

_PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


def get_system_prompt() -> str:
    """
    Return the fully interpolated Orion system prompt.

    The template file uses ``{user_name}`` as a placeholder that is
    replaced with the configured ``ORION_USER_NAME`` env var.
    """
    template_path = _PROMPT_DIR / "system_prompt.txt"

    if template_path.exists():
        template = template_path.read_text(encoding="utf-8")
    else:
        # Inline fallback if the file is missing
        template = (
            "You are Orion — an advanced voice-first AI assistant. "
            "You address the user as {user_name}. Be calm, precise, and efficient. "
            "Never be sycophantic. Keep spoken responses short and natural."
        )

    return template.format(user_name=config.user_name)
