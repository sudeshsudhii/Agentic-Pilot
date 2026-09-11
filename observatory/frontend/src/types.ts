export interface ObservatoryEvent {
  event_id: string;
  run_id: string;
  task_id: string;
  timestamp: string;
  event_type: string;
  status: string;
  step_index: number;
  message: string;
  metadata: Record<string, any>;
}

export interface RunSummary {
  run_id: string;
  task_id: string;
  input_text: string;
  status: string;
  created_at: string;
  completed_at?: string | null;
  duration_sec?: number | null;
  step_count: number;
  model: string;
  vision_status: string;
  error?: string | null;
}

export interface PerformanceMetrics {
  total_duration_sec: number;
  planner_duration_sec: number;
  vision_duration_sec: number;
  browser_duration_sec: number;
  verification_duration_sec: number;
  waiting_duration_sec: number;
  retry_duration_sec: number;
  model_latencies: Array<{
    model: string;
    type: string;
    duration_ms: number;
    timestamp: string;
  }>;
}

export interface SystemStatus {
  pilot_backend_connected: boolean;
  event_stream_connected: boolean;
  last_event_timestamp: string | null;
  last_event_age_sec: number | null;
  active_run_id: string | null;
  event_buffer_size: number;
}

export interface ExperienceItem {
  memory_id: string;
  type: string;
  task_id: string;
  content: any;
  tags: string[];
  created_at: string;
  access_count: number;
  training_eligible: boolean;
}
