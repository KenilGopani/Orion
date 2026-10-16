"""
Outcome listener — hear what the voice agent would say, without audio.
=====================================================================
Prints each approval outcome the voice agent would speak: approve or reject a
task in the dashboard while this runs, and the announcement appears here.

Run (with `make up` running):
    uv run python dev/listen_outcomes.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orion.config import config  # noqa: E402
from orion.voice_outcomes import OutcomeAnnouncer  # noqa: E402


def main() -> None:
    url = f"http://127.0.0.1:{config.port}/api/events/outcomes"
    print(f"Listening for approval outcomes at {url} (Ctrl-C to stop)\n")
    announcer = OutcomeAnnouncer(url, speak=lambda text: print(f"Orion: {text}", flush=True))
    try:
        asyncio.run(announcer.run())
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
