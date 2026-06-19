export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8765";

export type Task = {
  task_id: string;
  input_text: string;
  status: string;
  risk_level?: string | null;
  parsed_intent?: Record<string, unknown> | null;
  result?: Record<string, unknown> | null;
  error?: string | null;
  approval_id?: string | null;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
};

export type TaskEvent = {
  id: number;
  task_id: string;
  type: string;
  message: string;
  payload?: Record<string, unknown> | null;
  created_at: string;
};

export type Approval = {
  approval_id: string;
  task_id: string;
  risk_level: string;
  prompt: string;
  status: string;
  response?: string | null;
  created_at: string;
  decided_at?: string | null;
};

export type Settings = {
  setup_complete: boolean;
  ollama_base_url: string;
  ollama_model: string;
  debug_mode: boolean;
  auto_approve_low_risk: boolean;
};

export type PluginManifest = {
  plugin_id: string;
  name: string;
  sites: string[];
  actions: string[];
  risk_levels: Record<string, string>;
  network_permission: boolean;
};

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers ?? {}) },
    ...options
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(typeof body.detail === "string" ? body.detail : "Request failed");
  }
  return response.json() as Promise<T>;
}

export async function createTask(inputText: string): Promise<{ task_id: string; status: string; stream_url: string }> {
  return request("/api/tasks", {
    method: "POST",
    body: JSON.stringify({ input_text: inputText })
  });
}

export async function listTasks(): Promise<Task[]> {
  const body = await request<{ tasks: Task[] }>("/api/tasks");
  return body.tasks;
}

export async function getTask(taskId: string): Promise<Task> {
  return request(`/api/tasks/${taskId}`);
}

export async function cancelTask(taskId: string): Promise<Task> {
  return request(`/api/tasks/${taskId}`, { method: "DELETE" });
}

export async function listApprovals(): Promise<Approval[]> {
  const body = await request<{ approvals: Approval[] }>("/api/approvals");
  return body.approvals;
}

export async function respondApproval(approvalId: string, decision: "approved" | "rejected"): Promise<Approval> {
  return request(`/api/approvals/${approvalId}/respond`, {
    method: "POST",
    body: JSON.stringify({ decision })
  });
}

export async function getSettings(): Promise<Settings> {
  return request("/api/settings");
}

export async function updateSettings(settings: Partial<Settings>): Promise<Settings> {
  return request("/api/settings", {
    method: "PUT",
    body: JSON.stringify(settings)
  });
}

export async function listPlugins(): Promise<PluginManifest[]> {
  const body = await request<{ plugins: PluginManifest[] }>("/api/plugins");
  return body.plugins;
}

export type BrowserStatus = {
  open: boolean;
  task_id: string | null;
  url?: string | null;
  idle_seconds: number;
  timeout_minutes: number;
};

export async function closeBrowser(taskId: string): Promise<{ status: string; task_id: string }> {
  return request(`/api/tasks/${taskId}/close-browser`, { method: "POST" });
}

export async function getBrowserStatus(): Promise<BrowserStatus> {
  return request("/api/browser/status");
}
