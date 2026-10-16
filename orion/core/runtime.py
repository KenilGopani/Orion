"""
Runtime wiring — builds the one set of services an Orion process uses.

Nothing here runs at import time. ``build_runtime()`` is called once by the
app (or by a dev tool / test) and the resulting ``Runtime`` is passed to
whatever needs it, so every part of a process shares one engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from orion.config import Config, config as default_config
from orion.core.approvals import ApprovalGate
from orion.core.engine import ExecutionEngine, PlannedStep, default_registry
from orion.core.models import Task
from orion.core.planner import LLMPlanner
from orion.core.registry import ToolRegistry
from orion.db.event_store import PersistentEventStore
from orion.db.task_store import PersistentTaskStore
from orion.tools import all_tools

if TYPE_CHECKING:
    from orion.services.scheduler import OrionScheduler


def build_registry() -> ToolRegistry:
    """Return a registry holding every tool the engine can execute.

    That is every declared tool in ``orion.tools`` (also exposed to the voice
    LLM) plus the engine's internal fallbacks.
    """
    registry = default_registry()
    for tool in all_tools():
        registry.register(tool)
    return registry


@dataclass
class Runtime:
    """The services one Orion process shares. Build it with ``build_runtime``."""

    config: Config
    store: PersistentTaskStore
    events: PersistentEventStore
    registry: ToolRegistry
    approval_gate: ApprovalGate
    planner: LLMPlanner
    engine: ExecutionEngine
    #: Set by the app while it is serving and the scheduler is enabled.
    scheduler: OrionScheduler | None = None

    async def run_tool(self, tool_name: str, user_intent: str, **tool_args: Any) -> Task:
        """Run a single registered tool as a task, under the approval gate.

        This is the path every voice tool call takes: the voice LLM has already
        chosen the tool, so the planner is skipped, but the engine records the
        call and enforces approval exactly as for a planned step.
        """
        tool = self.registry.get(tool_name)
        return await self.engine.create_task_with_steps(
            user_intent=user_intent,
            steps=[
                PlannedStep(
                    name=tool_name,
                    description=tool.description,
                    tool_name=tool_name,
                    tool_args=tool_args,
                )
            ],
        )


def build_runtime(cfg: Config | None = None) -> Runtime:
    """Construct the services for one process.

    Opens no database connection; call ``orion.db.session.init_db()`` before
    the first task is created.
    """
    cfg = cfg or default_config
    store = PersistentTaskStore()
    events = PersistentEventStore()
    registry = build_registry()
    approval_gate = ApprovalGate(store)
    planner = LLMPlanner(registry=registry, llm_provider=cfg.llm_provider)
    engine = ExecutionEngine(
        store=store,
        events=events,
        registry=registry,
        approval_gate=approval_gate,
        planner=planner,
    )
    return Runtime(
        config=cfg,
        store=store,
        events=events,
        registry=registry,
        approval_gate=approval_gate,
        planner=planner,
        engine=engine,
    )
