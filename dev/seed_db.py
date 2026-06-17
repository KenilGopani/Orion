"""
Seed the Orion database with realistic fake tasks.

Creates tasks in different states (SUCCEEDED, AWAITING_APPROVAL, RUNNING)
so the dashboard can be developed without the voice pipeline.

Usage:
    uv run python dev/seed_db.py
    # or
    make seed
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from uuid import uuid4

# Ensure imports work from project root
sys.path.insert(0, ".")

from orion.db.session import init_db, get_session
from orion.db.models import TaskRecord, TaskStepRecord, ApprovalRecord, EventRecord


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _id() -> str:
    return str(uuid4())


def seed() -> None:
    """Populate the database with 3 realistic tasks."""
    init_db()

    # ── Task 1: SUCCEEDED — checked email ─────────────────────────
    t1_id = _id()
    s1_id = _id()
    t1_created = _utc_now() - timedelta(hours=2)

    task1 = TaskRecord(
        id=t1_id,
        user_intent="Check my email and summarise what's urgent",
        status="SUCCEEDED",
        created_at=t1_created,
        updated_at=t1_created + timedelta(seconds=3),
    )
    step1 = TaskStepRecord(
        id=s1_id,
        task_id=t1_id,
        name="check_email",
        description="Check email inbox via OpenClaw",
        status="SUCCEEDED",
        planned_tool_name="openclaw_send_email",
        planned_tool_args=json.dumps({"to": "inbox", "subject": "check", "body": "summary"}),
        tool_result_output=json.dumps({
            "message": "You have 3 unread emails. One from Priya about the deadline, "
                       "one GitHub PR review, and a Python Weekly newsletter."
        }),
        tool_result_success=True,
        created_at=t1_created,
        updated_at=t1_created + timedelta(seconds=3),
    )
    event1a = EventRecord(
        id=_id(), task_id=t1_id, event_type="task_started",
        payload=json.dumps({"intent": task1.user_intent}),
        created_at=t1_created,
    )
    event1b = EventRecord(
        id=_id(), task_id=t1_id, event_type="task_succeeded",
        payload=json.dumps({"duration_ms": 3000}),
        created_at=t1_created + timedelta(seconds=3),
    )

    # ── Task 2: AWAITING_APPROVAL — send WhatsApp ─────────────────
    t2_id = _id()
    s2_id = _id()
    a2_id = _id()
    t2_created = _utc_now() - timedelta(minutes=30)

    task2 = TaskRecord(
        id=t2_id,
        user_intent="Send a WhatsApp to Priya: I'll be 10 minutes late",
        status="AWAITING_APPROVAL",
        created_at=t2_created,
        updated_at=t2_created + timedelta(seconds=1),
    )
    step2 = TaskStepRecord(
        id=s2_id,
        task_id=t2_id,
        name="send_whatsapp",
        description="Send WhatsApp message through OpenClaw backend",
        status="AWAITING_APPROVAL",
        planned_tool_name="openclaw_send_whatsapp",
        planned_tool_args=json.dumps({
            "recipient": "Priya",
            "message": "I'll be 10 minutes late",
        }),
        created_at=t2_created,
        updated_at=t2_created + timedelta(seconds=1),
    )
    approval2 = ApprovalRecord(
        id=a2_id,
        task_id=t2_id,
        step_id=s2_id,
        tool_name="openclaw_send_whatsapp",
        reason="Tool safety level: EXTERNAL_SIDE_EFFECT — sends messages externally",
        created_at=t2_created + timedelta(seconds=1),
    )
    event2a = EventRecord(
        id=_id(), task_id=t2_id, event_type="task_started",
        payload=json.dumps({"intent": task2.user_intent}),
        created_at=t2_created,
    )
    event2b = EventRecord(
        id=_id(), task_id=t2_id, event_type="approval_required",
        payload=json.dumps({"tool": "openclaw_send_whatsapp", "approval_id": a2_id}),
        created_at=t2_created + timedelta(seconds=1),
    )

    # ── Task 3: RUNNING — write a file ────────────────────────────
    t3_id = _id()
    s3_id = _id()
    t3_created = _utc_now() - timedelta(minutes=5)

    task3 = TaskRecord(
        id=t3_id,
        user_intent="Write a README.md for my project",
        status="RUNNING",
        created_at=t3_created,
        updated_at=t3_created + timedelta(seconds=1),
    )
    step3 = TaskStepRecord(
        id=s3_id,
        task_id=t3_id,
        name="write_file",
        description="Write file through OpenClaw backend",
        status="RUNNING",
        planned_tool_name="openclaw_write_file",
        planned_tool_args=json.dumps({
            "path": "README.md",
            "content": "# My Project\n\nAwesome project description here.",
        }),
        created_at=t3_created,
        updated_at=t3_created + timedelta(seconds=1),
    )
    event3 = EventRecord(
        id=_id(), task_id=t3_id, event_type="task_started",
        payload=json.dumps({"intent": task3.user_intent}),
        created_at=t3_created,
    )

    # ── Conversation messages ─────────────────────────────────────
    from orion.db.models import ConversationMessage

    session_id = "seed-session-001"
    conv_base = _utc_now() - timedelta(hours=1)

    conv_msgs = [
        ConversationMessage(
            id=_id(), session_id=session_id, role="user",
            content="Check my email and tell me what's urgent",
            timestamp=conv_base,
        ),
        ConversationMessage(
            id=_id(), session_id=session_id, role="assistant",
            content="You have 3 unread emails, sir. The most urgent is from Priya about tomorrow's deadline. The other two are a GitHub notification and a newsletter.",
            timestamp=conv_base + timedelta(seconds=4),
        ),
        ConversationMessage(
            id=_id(), session_id=session_id, role="user",
            content="Send a WhatsApp to Priya saying I'll be 10 minutes late",
            timestamp=conv_base + timedelta(minutes=5),
        ),
        ConversationMessage(
            id=_id(), session_id=session_id, role="assistant",
            content="That will require your approval before I send it, sir. Please approve the action in the dashboard.",
            timestamp=conv_base + timedelta(minutes=5, seconds=2),
        ),
        ConversationMessage(
            id=_id(), session_id=session_id, role="user",
            content="Remember that Priya's project deadline is June 20th",
            timestamp=conv_base + timedelta(minutes=10),
        ),
        ConversationMessage(
            id=_id(), session_id=session_id, role="assistant",
            content="Noted, sir. I'll remember that for future reference.",
            timestamp=conv_base + timedelta(minutes=10, seconds=1),
        ),
    ]

    # ── Insert everything ─────────────────────────────────────────
    with get_session() as session:
        for obj in [
            task1, step1, event1a, event1b,
            task2, step2, approval2, event2a, event2b,
            task3, step3, event3,
            *conv_msgs,
        ]:
            session.add(obj)
        session.commit()

    print("✓ Seeded database for dashboard development:")
    print(f"  • {t1_id[:8]}… — SUCCEEDED (email check)")
    print(f"  • {t2_id[:8]}… — AWAITING_APPROVAL (WhatsApp)")
    print(f"  • {t3_id[:8]}… — RUNNING (write file)")
    print(f"  • {len(conv_msgs)} conversation messages")
    print(f"\nDatabase: ~/.orion/orion.db")


if __name__ == "__main__":
    seed()
