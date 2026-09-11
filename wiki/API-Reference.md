# API Reference

Agentic Pilot exposes dual REST and WebSocket APIs across its core and telemetry services.

---

## Service Endpoints Overview

| Service | Port | Base Path | Primary Protocol | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **Pilot Core API** | `8765` | `http://127.0.0.1:8765` | REST + WebSocket + SSE | Task dispatch, approvals, health checks, settings. |
| **Observatory API** | `8766` | `http://127.0.0.1:8766` | REST + WebSocket | Telemetry streaming, run history, performance metrics. |

---

## 1. Pilot Core API (`:8765`)

### Task Management

#### `POST /api/tasks`
Submits a new natural language task instruction for autonomous execution.

* **Request Body**:
```json
{
  "input_text": "Navigate to news.ycombinator.com and extract the title of the top story",
  "session_id": "optional-session-uuid"
}
```

* **Response (200 OK)**:
```json
{
  "task_id": "8f3a1b02-5c94-4d2a-89a1-0e1d2f3a4b5c",
  "status": "running",
  "message": "Task accepted and dispatched to LangGraph execution engine"
}
```

#### `GET /api/tasks/{task_id}`
Retrieves the execution status, current action, and results for a specific task.

* **Response (200 OK)**:
```json
{
  "task_id": "8f3a1b02-5c94-4d2a-89a1-0e1d2f3a4b5c",
  "status": "completed",
  "current_step_index": 3,
  "final_answer": "Top story: 'Show HN: Local Autonomous Web Agent'",
  "action_history": [
    {
      "action_type": "navigate",
      "success": true,
      "duration_ms": 1240
    }
  ],
  "error": null
}
```

#### `POST /api/tasks/{task_id}/cancel`
Aborts an in-flight autonomous agent task and gracefully recycles browser resources.

---

### System Health & Status

#### `GET /api/health`
Returns connectivity and health metrics for underlying subsystems.

* **Response (200 OK)**:
```json
{
  "status": "healthy",
  "ollama": {
    "connected": true,
    "installed_models": ["qwen2.5:1.5b", "moondream:latest"]
  },
  "database": {
    "connected": true,
    "path": "~/.pilot/data.db"
  },
  "browser": {
    "pool_active": true,
    "instances": 1
  }
}
```

---

### Human-in-the-Loop Approvals

#### `GET /api/approvals`
Lists pending risk or CAPTCHA approval requests awaiting human confirmation.

#### `POST /api/approvals/{approval_id}`
Submits a decision for a pending approval checkpoint.

* **Request Body**:
```json
{
  "approved": true,
  "notes": "Human solved CAPTCHA manually in browser"
}
```

---

### Real-Time Event Streams

#### `WebSocket /ws/agent`
Bi-directional socket streaming task progress and step updates directly to the primary user interface.

#### `GET /api/observability/events`
Server-Sent Events (SSE) endpoint providing a continuous feed of JSON-serialized agent events.

---

## 2. Observatory Telemetry API (`:8766`)

### System & Stream Telemetry

#### `GET /api/status`
Returns real-time connection telemetry for the developer observatory.

* **Response (200 OK)**:
```json
{
  "pilot_backend_connected": true,
  "event_stream_connected": true,
  "last_event_timestamp": "2026-09-11T08:15:30.123Z",
  "last_event_age_sec": 4.2,
  "active_run_id": "8f3a1b02-5c94-4d2a-89a1-0e1d2f3a4b5c",
  "event_buffer_size": 150
}
```

---

### Historical Runs & Metrics

#### `GET /api/runs?limit=50`
Returns a paginated list of historical agent runs.

* **Response (200 OK)**:
```json
[
  {
    "run_id": "8f3a1b02-5c94-4d2a-89a1-0e1d2f3a4b5c",
    "task_prompt": "Search flight prices on duckduckgo.com",
    "status": "completed",
    "start_time": "2026-09-11T08:10:00.000Z",
    "duration_sec": 24.5,
    "step_count": 5
  }
]
```

#### `GET /api/runs/{run_id}`
Returns complete event traces, final state, and performance summaries for a specific run.

#### `GET /api/runs/{run_id}/performance`
Returns subsystem latency breakdowns for performance profiling.

* **Response (200 OK)**:
```json
{
  "total_duration_sec": 24.5,
  "planner_duration_sec": 8.2,
  "vision_duration_sec": 3.1,
  "browser_duration_sec": 9.4,
  "verification_duration_sec": 2.2,
  "waiting_duration_sec": 1.6,
  "retry_duration_sec": 0.0,
  "model_latencies": [
    { "model": "qwen2.5:1.5b", "call_count": 4, "total_ms": 8200 },
    { "model": "moondream", "call_count": 1, "total_ms": 3100 }
  ]
}
```

---

### Real-Time Telemetry Socket

#### `WebSocket /ws`
Bi-directional real-time feed streaming `ObservatoryEvent` objects to the Observatory dashboard. Supports client-to-server `"ping"` messages for keep-alive with server `"pong"` responses.

---

*Related Pages:*
* [[Agent Observatory|Agent-Observatory]]
* [[Configuration|Configuration]]
* [[Development Guide|Development-Guide]]
