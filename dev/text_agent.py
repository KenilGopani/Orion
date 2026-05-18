"""
Text Agent — CLI version of Orion for development.
====================================================
A terminal-based interface that accepts typed text instead of voice input.
Tests the full execution engine pipeline without LiveKit, STT, or TTS.

Run:
    uv run python dev/text_agent.py
    # or: make dev
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orion.config import config
from orion.core.runtime import engine, store


BANNER = """
╔══════════════════════════════════════════════════╗
║              Orion — Text Mode (Dev)             ║
╠══════════════════════════════════════════════════╣
║  Commands:                                       ║
║    tasks   — list recent tasks                   ║
║    events  — show events for last task           ║
║    health  — check system status                 ║
║    exit    — quit                                ║
║  Or type any voice command to test the engine.   ║
╚══════════════════════════════════════════════════╝
"""


async def _check_health() -> None:
    """Print system health status."""
    from bridge import openclaw_client

    openclaw_ok = await openclaw_client.health_check()
    status = "✓ ONLINE" if openclaw_ok else "✗ OFFLINE"

    print(f"\n  System Health:")
    print(f"    DEV_MODE:       {config.dev_mode}")
    print(f"    MOCK_OPENCLAW:  {config.mock_openclaw}")
    print(f"    OpenClaw:       {status} ({config.openclaw_url})")
    print(f"    STT Provider:   {config.stt_provider}")
    print(f"    LLM Provider:   {config.llm_provider}")
    print(f"    TTS Provider:   {config.tts_provider}")
    print()


async def main() -> None:
    print(BANNER)

    if config.dev_mode:
        print("  ⚡ Running in DEV_MODE\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nGoodbye, sir.")
            break

        if not user_input:
            continue

        if user_input.lower() == "exit":
            print("\nGoodbye, sir.")
            break

        if user_input.lower() == "tasks":
            tasks = store.list_tasks()
            if not tasks:
                print("  No tasks yet.\n")
                continue
            print()
            for t in tasks[-10:]:
                status_icon = {
                    "SUCCEEDED": "✓",
                    "FAILED": "✗",
                    "AWAITING_APPROVAL": "⏳",
                    "RUNNING": "⟳",
                    "PENDING": "○",
                    "PLANNING": "◐",
                    "CANCELLED": "⊘",
                }.get(t.status, "?")
                print(f"  {status_icon} [{t.status:20s}] {t.user_intent}")
            print()
            continue

        if user_input.lower() == "events":
            tasks = store.list_tasks()
            if not tasks:
                print("  No tasks yet.\n")
                continue
            last_task = tasks[-1]
            from orion.core.runtime import events

            task_events = events.list_events(last_task.id)
            if not task_events:
                print(f"  No events for task: {last_task.user_intent}\n")
                continue
            print(f"\n  Events for: {last_task.user_intent}")
            for evt in task_events:
                ts = evt.timestamp.strftime("%H:%M:%S")
                print(f"    {ts}  {evt.event_type}")
            print()
            continue

        if user_input.lower() == "health":
            await _check_health()
            continue

        # ── Execute the intent through the engine ────────────────
        print("Orion: (processing...)")
        try:
            task = await engine.create_task(user_input)
        except Exception as exc:
            print(f"Orion: I'm afraid something went wrong, sir. Error: {exc}\n")
            continue

        # Report result
        if task.status == "SUCCEEDED":
            if task.steps and task.steps[-1].tool_result:
                result = task.steps[-1].tool_result
                if result.output:
                    output_text = result.output.get("message") or result.output.get("echoed") or str(result.output)
                    print(f"Orion: {output_text}")
                else:
                    print(f"Orion: Done, sir.")
            else:
                print(f"Orion: Task completed successfully, sir.")
        elif task.status == "FAILED":
            print(f"Orion: I'm afraid that didn't work, sir. {task.error or ''}")
        elif task.status == "AWAITING_APPROVAL":
            pending = store.get_latest_pending_approval(task.id)
            if pending:
                print(f"\n  ⚠️  Approval required for: {pending.tool_name}")
                print(f"     Safety level: {pending.reason}")
                answer = input("     Approve? (y/n): ").strip().lower()
                if answer in {"y", "yes"}:
                    try:
                        resumed = await engine.resume_task_after_approval(
                            task.id, approved_by="dev_user"
                        )
                        if resumed.status == "SUCCEEDED":
                            if resumed.steps and resumed.steps[-1].tool_result:
                                result = resumed.steps[-1].tool_result
                                output_text = result.output.get("message", "Done, sir.")
                                print(f"Orion: {output_text}")
                            else:
                                print(f"Orion: Approved and executed, sir.")
                        else:
                            print(f"Orion: Task status → {resumed.status}")
                    except Exception as exc:
                        print(f"Orion: Approval failed: {exc}")
                else:
                    print("Orion: Understood, action cancelled, sir.")
        else:
            print(f"Orion: Task ended with status {task.status}.")

        print()


if __name__ == "__main__":
    asyncio.run(main())
