"""
Input types that limit what a hijacked voice LLM can smuggle into an
OpenClaw instruction.

OpenClaw receives natural language, so a tool argument such as a search query
is spliced into instructions. Two defences, both documented in SECURITY.md:

- ``Line``: fields that are naturally one line (queries, paths, recipients,
  subjects) reject line breaks and are length-capped. Prompt injections lean
  on newlines to start a fresh "instruction"; this closes that channel. The
  constraint is part of the JSON schema, so the voice LLM sees it too.
- ``q()``: every value is rendered as a JSON string literal, and OpenClaw's
  system prompt says quoted values are data, never instructions.

Neither is a guarantee — a model can still be talked into misusing a quoted
value — which is why read-only tools also run on an OpenClaw agent that has
no dangerous tools (see orion/openclaw_setup.py).
"""

from __future__ import annotations

import json
from typing import Annotated

from pydantic import AfterValidator, StringConstraints

LINE_MAX = 500


def q(value: object) -> str:
    """Render a value as a quoted, escaped literal for an OpenClaw instruction."""
    return json.dumps(str(value), ensure_ascii=False)


def _no_control_chars(value: str) -> str:
    if any(ord(ch) < 32 and ch != "\t" for ch in value):
        raise ValueError("must be a single line with no control characters")
    return value


#: A single line of text: no line breaks or control characters, length-capped.
Line = Annotated[
    str,
    StringConstraints(max_length=LINE_MAX, pattern=r"^[^\r\n]*$"),
    AfterValidator(_no_control_chars),
]


def _http_url(value: str) -> str:
    if not value.lower().startswith(("http://", "https://")):
        raise ValueError("only http:// and https:// URLs can be opened")
    return value


#: A web URL. Other schemes (file:, javascript:, custom app handlers) are refused.
HttpUrl = Annotated[Line, AfterValidator(_http_url)]
