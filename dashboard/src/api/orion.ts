/**
 * Orion API Client
 * Typed HTTP client for all Orion Runtime API endpoints.
 */

// Same origin: served by `orion up`, or proxied by the Vite dev server.
const API_BASE = "/api";

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

export interface VoiceToken {
  url: string;
  token: string;
  room: string;
}

export interface SchedulerJob {
  id: string;
  name: string;
  schedule: string;
  enabled: boolean;
  next_run: string | null;
}

// ── API Client ───────────────────────────────────────────────────

/** Parse a JSON response, throwing on non-2xx so callers can't mistake an error for success. */
async function json<T>(r: Response): Promise<T> {
  if (!r.ok) {
    const body = await r.json().catch(() => null);
    throw new Error(body?.detail ?? `HTTP ${r.status}`);
  }
  return r.json();
}

// State-changing routes require the per-install token. It's fetched once from
// the same origin; a page on another site can't read it (no CORS grant).
let tokenRequest: Promise<string> | null = null;

function apiToken(): Promise<string> {
  tokenRequest ??= fetch(`${API_BASE}/auth/token`)
    .then(json<{ token: string }>)
    .then((body) => body.token)
    .catch((err) => {
      tokenRequest = null; // retry on the next call
      throw err;
    });
  return tokenRequest;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const token = await apiToken();
  return fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Orion-Token": token },
    body: JSON.stringify(body),
  }).then(json<T>);
}

export const orionApi = {
  health: (): Promise<HealthResponse> =>
    fetch(`${API_BASE}/health`).then(json<HealthResponse>),

  getTasks: (): Promise<Task[]> =>
    fetch(`${API_BASE}/tasks`).then(json<Task[]>),

  getTask: (id: string): Promise<Task> =>
    fetch(`${API_BASE}/tasks/${id}`).then(json<Task>),

  getTaskEvents: (id: string): Promise<RuntimeEvent[]> =>
    fetch(`${API_BASE}/tasks/${id}/events`).then(json<RuntimeEvent[]>),

  approveTask: (id: string): Promise<Task> =>
    post<Task>(`/tasks/${id}/approve`, { approved_by: "dashboard_user" }),

  rejectTask: (id: string): Promise<Task> =>
    post<Task>(`/tasks/${id}/reject`, { rejected_by: "dashboard_user" }),

  getConversations: (): Promise<ConversationMessage[]> =>
    fetch(`${API_BASE}/conversations`).then(json<ConversationMessage[]>),

  getVoiceToken: (): Promise<VoiceToken> =>
    fetch(`${API_BASE}/voice/token`).then(json<VoiceToken>),

  getSchedulerJobs: (): Promise<SchedulerJob[]> =>
    fetch(`${API_BASE}/scheduler/jobs`).then(json<SchedulerJob[]>),

  streamEvents: (
    id: string,
    onEvent: (e: RuntimeEvent) => void
  ): EventSource => {
    const es = new EventSource(`${API_BASE}/tasks/${id}/stream`);
    es.onmessage = (e) => onEvent(JSON.parse(e.data));
    return es;
  },
};
