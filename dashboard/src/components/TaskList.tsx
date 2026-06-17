import type { Task } from "../api/orion";

interface TaskListProps {
  tasks: Task[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMin = Math.floor(diffMs / 60000);

  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHrs = Math.floor(diffMin / 60);
  if (diffHrs < 24) return `${diffHrs}h ago`;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export default function TaskList({ tasks, selectedId, onSelect }: TaskListProps) {
  // Show most recent tasks first
  const sorted = [...tasks].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );

  return (
    <div className="panel" id="task-list-panel">
      <div className="panel__header">
        <span className="panel__title">Tasks</span>
        <span className="panel__count">{tasks.length}</span>
      </div>
      <div className="panel__body">
        {sorted.length === 0 ? (
          <div className="panel__empty">No tasks yet</div>
        ) : (
          sorted.map((task) => (
            <div
              key={task.id}
              className={`task-item ${
                selectedId === task.id ? "task-item--selected" : ""
              }`}
              onClick={() => onSelect(task.id)}
              id={`task-${task.id}`}
            >
              <div className="task-item__top">
                <span className="task-item__intent">{task.user_intent}</span>
                <span className="task-item__time">
                  {formatTime(task.created_at)}
                </span>
              </div>
              <span className={`status-badge status-badge--${task.status}`}>
                {task.status.replace("_", " ")}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
