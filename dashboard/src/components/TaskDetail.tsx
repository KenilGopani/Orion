import { useEffect, useState } from "react";
import { orionApi, type Task, type RuntimeEvent } from "../api/orion";

interface TaskDetailProps {
  taskId: string | null;
  tasks: Task[];
}

const STEP_ICONS: Record<string, string> = {
  PENDING: "○",
  RUNNING: "◎",
  AWAITING_APPROVAL: "⏸",
  SUCCEEDED: "✓",
  FAILED: "✗",
  SKIPPED: "–",
};

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export default function TaskDetail({ taskId, tasks }: TaskDetailProps) {
  const [events, setEvents] = useState<RuntimeEvent[]>([]);
  const task = tasks.find((t) => t.id === taskId) ?? null;

  useEffect(() => {
    if (!taskId) {
      setEvents([]);
      return;
    }
    orionApi.getTaskEvents(taskId).then(setEvents).catch(() => setEvents([]));
    // Re-fetch events when task list updates (which includes status changes)
  }, [taskId, tasks]);

  if (!task) {
    return (
      <div className="panel" id="task-detail-panel">
        <div className="panel__header">
          <span className="panel__title">Task Detail</span>
        </div>
        <div className="panel__body">
          <div className="panel__empty">Select a task to view details</div>
        </div>
      </div>
    );
  }

  return (
    <div className="panel" id="task-detail-panel">
      <div className="panel__header">
        <span className="panel__title">Task Detail</span>
        <span className={`status-badge status-badge--${task.status}`}>
          {task.status.replace("_", " ")}
        </span>
      </div>

      <div className="panel__body">
        {/* Intent */}
        <div className="task-detail__intent">
          <div className="task-detail__intent-text">{task.user_intent}</div>
          <div className="task-detail__meta">
            <span className="task-detail__meta-item">
              ID: {task.id.slice(0, 8)}…
            </span>
            <span className="task-detail__meta-item">
              {formatTimestamp(task.created_at)}
            </span>
            <span className="task-detail__meta-item">
              {task.steps.length} step{task.steps.length !== 1 ? "s" : ""}
            </span>
          </div>
        </div>

        {/* Step Timeline */}
        {task.steps.length > 0 && (
          <div className="step-timeline">
            <div className="step-timeline__title">Execution Plan</div>
            {task.steps.map((step) => (
              <div key={step.id} className="step-item">
                <div className={`step-item__icon step-item__icon--${step.status}`}>
                  {STEP_ICONS[step.status] ?? "?"}
                </div>
                <div className="step-item__content">
                  <div className="step-item__name">{step.name}</div>
                  <div className="step-item__desc">{step.description}</div>
                  {step.planned_tool_name && (
                    <span className="step-item__tool">
                      {step.planned_tool_name}
                    </span>
                  )}
                  {step.error && (
                    <div className="step-item__error">{step.error}</div>
                  )}
                  {step.tool_result && step.tool_result.success && (
                    <div className="step-item__result">
                      {JSON.stringify(step.tool_result.output, null, 2)}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Error */}
        {task.error && (
          <div style={{ padding: "12px 18px" }}>
            <div className="step-item__error">{task.error}</div>
          </div>
        )}

        {/* Events */}
        {events.length > 0 && (
          <div className="step-timeline">
            <div className="step-timeline__title">
              Event Log ({events.length})
            </div>
            {events.map((evt) => (
              <div key={evt.id} className="step-item">
                <div
                  className="step-item__icon step-item__icon--SUCCEEDED"
                  style={{ width: 18, height: 18, fontSize: "0.55rem" }}
                >
                  •
                </div>
                <div className="step-item__content">
                  <div className="step-item__name" style={{ fontSize: "0.75rem" }}>
                    {evt.event_type}
                  </div>
                  <div className="step-item__desc">
                    {formatTimestamp(evt.timestamp)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
