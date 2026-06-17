import type { SchedulerJob } from "../api/orion";

interface SchedulerPanelProps {
  jobs: SchedulerJob[];
}

function formatNextRun(iso: string | null): string {
  if (!iso) return "Not scheduled";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export default function SchedulerPanel({ jobs }: SchedulerPanelProps) {
  return (
    <div className="panel scheduler-panel" id="scheduler-panel">
      <div className="panel__header">
        <span className="panel__title">Scheduled Actions</span>
        {jobs.length > 0 && (
          <span className="panel__count">{jobs.length}</span>
        )}
      </div>
      <div className="panel__body">
        {jobs.length === 0 ? (
          <div className="panel__empty">No scheduled jobs</div>
        ) : (
          <div className="scheduler-list">
            {jobs.map((job) => (
              <div
                key={job.id}
                className="scheduler-item"
                id={`job-${job.id}`}
              >
                <div className="scheduler-item__header">
                  <span className="scheduler-item__name">
                    {job.name}
                  </span>
                  <span
                    className={`scheduler-badge ${
                      job.enabled ? "scheduler-badge--active" : "scheduler-badge--disabled"
                    }`}
                  >
                    {job.enabled ? "Active" : "Disabled"}
                  </span>
                </div>
                <div className="scheduler-item__details">
                  <span className="scheduler-item__cron">
                    Schedule: <code>{job.schedule}</code>
                  </span>
                  {job.enabled && job.next_run && (
                    <span className="scheduler-item__next">
                      Next Run: {formatNextRun(job.next_run)}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
