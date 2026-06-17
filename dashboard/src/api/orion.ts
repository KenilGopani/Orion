/**
 * Orion API Client
 * Typed HTTP client for all Orion Runtime API endpoints.
 */

const API_BASE = "http://localhost:8010";

// ── Types ────────────────────────────────────────────────────────

export interface HealthResponse {
  status: string;
  dev_mode: boolean;
  mock_openclaw: boolean;
  dependencies: {
    openclaw: boolean;
  };
  providers: {
    stt: string;
    llm: string;
    tts: string;
  };
}

export interface ToolCall {
  id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  safety_level: string;
  started_at: string;
  finished_at: string | null;
}

export interface ToolResult {
  success: boolean;
  output: Record<string, unknown>;
  error: string | null;
}

export interface TaskStep {
  id: string;
  name: string;
  description: string;
  status: "PENDING" | "RUNNING" | "AWAITING_APPROVAL" | "SUCCEEDED" | "FAILED" | "SKIPPED";
  planned_tool_name: string | null;
  planned_tool_args: Record<string, unknown>;
  tool_call: ToolCall | null;
  tool_result: ToolResult | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface Task {
  id: string;
  user_intent: string;
  status: "PENDING" | "PLANNING" | "RUNNING" | "AWAITING_APPROVAL" | "SUCCEEDED" | "FAILED" | "CANCELLED";
  steps: TaskStep[];
  created_at: string;
  updated_at: string;
  error: string | null;
}

export interface RuntimeEvent {
  id: string;
  task_id: string;
  event_type: string;
  timestamp: string;
  payload: Record<string, unknown>;
}

export interface ConversationMessage {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

// ── API Client ───────────────────────────────────────────────────

export const orionApi = {
  health: (): Promise<HealthResponse> =>
    fetch(`${API_BASE}/health`).then((r) => r.json()),

  getTasks: (): Promise<Task[]> =>
    fetch(`${API_BASE}/tasks`).then((r) => r.json()),

  getTask: (id: string): Promise<Task> =>
    fetch(`${API_BASE}/tasks/${id}`).then((r) => r.json()),

  getTaskEvents: (id: string): Promise<RuntimeEvent[]> =>
    fetch(`${API_BASE}/tasks/${id}/events`).then((r) => r.json()),

  approveTask: (id: string): Promise<Task> =>
    fetch(`${API_BASE}/tasks/${id}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approved_by: "dashboard_user" }),
    }).then((r) => r.json()),

  rejectTask: (id: string): Promise<Task> =>
    fetch(`${API_BASE}/tasks/${id}/reject`, {
      method: "POST",
    }).then((r) => r.json()),

  getConversations: (): Promise<ConversationMessage[]> =>
    fetch(`${API_BASE}/conversations`).then((r) => r.json()),

  streamEvents: (
    id: string,
    onEvent: (e: RuntimeEvent) => void
  ): EventSource => {
    const es = new EventSource(`${API_BASE}/tasks/${id}/stream`);
    es.onmessage = (e) => onEvent(JSON.parse(e.data));
    return es;
  },
};
