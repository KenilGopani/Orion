import { useState } from "react";
import StatusBar from "./components/StatusBar";
import TaskList from "./components/TaskList";
import TaskDetail from "./components/TaskDetail";
import ApprovalPanel from "./components/ApprovalPanel";
import ConversationLog from "./components/ConversationLog";
import SchedulerPanel from "./components/SchedulerPanel";
import { useHealth, useTasks, useConversations, useToast, useSchedulerJobs } from "./hooks/useOrion";

export default function App() {
  const health = useHealth(5000);
  const { tasks, refetch } = useTasks(2000);
  const conversations = useConversations(3000);
  const { toasts, addToast } = useToast();
  const { jobs } = useSchedulerJobs(5000);

  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);

  return (
    <div className="app-layout">
      <StatusBar health={health} />

      <main className="main-content">
        <div className="sidebar">
          <TaskList
            tasks={tasks}
            selectedId={selectedTaskId}
            onSelect={setSelectedTaskId}
          />
          <SchedulerPanel jobs={jobs} />
        </div>

        <TaskDetail taskId={selectedTaskId} tasks={tasks} />

        <ApprovalPanel
          tasks={tasks}
          onAction={addToast}
          onRefetch={refetch}
        />

        <ConversationLog messages={conversations} />
      </main>

      {/* Toast notifications */}
      {toasts.length > 0 && (
        <div className="toast-container">
          {toasts.map((t) => (
            <div key={t.id} className={`toast toast--${t.type}`}>
              {t.message}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
