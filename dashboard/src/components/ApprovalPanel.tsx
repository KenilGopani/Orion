import { useState } from "react";
import { orionApi, type Task } from "../api/orion";

interface ApprovalPanelProps {
  tasks: Task[];
  onAction: (message: string, type: "success" | "error") => void;
  onRefetch: () => void;
}

export default function ApprovalPanel({
  tasks,
  onAction,
  onRefetch,
}: ApprovalPanelProps) {
  const [loading, setLoading] = useState<string | null>(null);

  const pendingTasks = tasks.filter(
    (t) => t.status === "AWAITING_APPROVAL"
  );

  const handleApprove = async (taskId: string) => {
    setLoading(taskId + "-approve");
    try {
      await orionApi.approveTask(taskId);
      onAction("Task approved — executing now", "success");
      onRefetch();
    } catch {
      onAction("Failed to approve task", "error");
    } finally {
      setLoading(null);
    }
  };

  const handleReject = async (taskId: string) => {
    setLoading(taskId + "-reject");
    try {
      await orionApi.rejectTask(taskId);
      onAction("Task rejected", "success");
      onRefetch();
    } catch {
      onAction("Failed to reject task", "error");
    } finally {
      setLoading(null);
    }
  };

  return (
    <div className="panel" id="approval-panel">
      <div className="panel__header">
        <span className="panel__title">Pending Approvals</span>
        {pendingTasks.length > 0 && (
          <span className="panel__count">{pendingTasks.length}</span>
        )}
      </div>
      <div className="panel__body">
        {pendingTasks.length === 0 ? (
          <div className="panel__empty">No pending approvals</div>
        ) : (
          pendingTasks.map((task) => {
            // Find the step that's awaiting approval
            const awaitingStep = task.steps.find(
              (s) => s.status === "AWAITING_APPROVAL"
            );
            const toolName =
              awaitingStep?.planned_tool_name ?? "Unknown tool";
            const toolArgs = awaitingStep?.planned_tool_args ?? {};

            return (
              <div key={task.id} className="approval-card" id={`approval-${task.id}`}>
                <div className="approval-card__tool">{toolName}</div>
                <div className="approval-card__intent">
                  {task.user_intent}
                </div>
                {Object.keys(toolArgs).length > 0 && (
                  <div className="approval-card__args">
                    {Object.entries(toolArgs).map(([key, val]) => (
                      <div key={key}>
                        <strong>{key}:</strong> {String(val)}
                      </div>
                    ))}
                  </div>
                )}
                <div className="approval-card__actions">
                  <button
                    className="btn btn--approve"
                    onClick={() => handleApprove(task.id)}
                    disabled={loading !== null}
                    id={`approve-btn-${task.id}`}
                  >
                    {loading === task.id + "-approve"
                      ? "Approving…"
                      : "✓ Approve"}
                  </button>
                  <button
                    className="btn btn--reject"
                    onClick={() => handleReject(task.id)}
                    disabled={loading !== null}
                    id={`reject-btn-${task.id}`}
                  >
                    {loading === task.id + "-reject"
                      ? "Rejecting…"
                      : "✗ Reject"}
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
