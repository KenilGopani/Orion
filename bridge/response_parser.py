"""
Response Parser
===============
Cleans raw OpenClaw output so it is safe and natural for TTS playback.

Rules:
- Strip all markdown formatting (bold, headers, code blocks, links)
- Remove bullet points and numbered lists
- Remove raw JSON
- Collapse excessive whitespace
- Truncate very long responses to keep voice output concise
"""

from __future__ import annotations

import re

# Maximum characters for a single spoken response (~45 seconds of speech)
_MAX_TTS_LENGTH = 800


def clean_for_tts(raw_text: str) -> str:
    """
    Transform raw LLM / OpenClaw output into clean spoken English.

    Parameters
    ----------
    raw_text : str
        The raw response text, potentially containing markdown, JSON, etc.

    Returns
    -------
    str
        A clean, natural-language string suitable for TTS.
    """
    text = raw_text

    # Remove code blocks (``` ... ```)
    text = re.sub(r"```[\s\S]*?```", "", text)

    # Remove inline code (`...`)
    text = re.sub(r"`([^`]*)`", r"\1", text)

    # Remove markdown headers (## Header)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)

    # Remove bold/italic markers
    text = re.sub(r"\*{1,3}([^*]*)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,3}([^_]*)_{1,3}", r"\1", text)

    # Remove markdown links [text](url) → text
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)

    # Remove raw URLs
    text = re.sub(r"https?://\S+", "", text)

    # Remove bullet points and numbered lists
    text = re.sub(r"^\s*[-*•]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)

    # Remove any remaining JSON-like blocks { ... }
    text = re.sub(r"\{[^{}]*\}", "", text)

    # Collapse multiple newlines into a single space
    text = re.sub(r"\n+", " ", text)

    # Collapse multiple spaces
    text = re.sub(r"\s{2,}", " ", text)

    text = text.strip()

    # Truncate if too long for comfortable voice delivery
    if len(text) > _MAX_TTS_LENGTH:
        # Try to cut at a sentence boundary
        truncated = text[:_MAX_TTS_LENGTH]
        last_period = truncated.rfind(".")
        if last_period > _MAX_TTS_LENGTH // 2:
            text = truncated[: last_period + 1]
        else:
            text = truncated.rstrip() + "…"

    return text if text else "The task completed but returned no details."
