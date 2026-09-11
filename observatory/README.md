# PILOT AGENT OBSERVATORY

**Pilot Agent Observatory** is a dedicated real-time developer and engineering dashboard for inspecting, tracing, and monitoring the internal execution lifecycle of the local-first Pilot browser agent.

---

## 1. Architectural Overview

The Observatory is built as an independent, read-only system running on a separate port and process from the existing Pilot workbench.

```
Pilot Workbench (:1420)
       │
       ▼
Pilot Core API & LangGraph (:8765)
       │
       │ WebSocket /ws/observability  (Fallback: SSE /api/observability/stream)
       ▼
Observatory Backend Proxy (:8766)
       │
       │ WebSocket /ws
       ▼
Agent Observatory Dashboard (:3001)
```

### Port Mapping
* **Pilot Frontend:** `http://127.0.0.1:1420` *(existing, unmodified)*
* **Pilot Backend Core:** `http://127.0.0.1:8765` *(existing, augmented with telemetry broadcaster)*
* **Observatory Backend API:** `http://127.0.0.1:8766` *(new, read-only event stream aggregator)*
* **Observatory Frontend Dashboard:** `http://127.0.0.1:3001` *(new, independent Vite + React developer UI)*

---

## 2. Key Design Guarantees

* **Strictly Read-Only:** The Observatory never executes browser automation, makes decisions, modifies Qwen model weights, or duplicates execution logic.
* **No Fake Data:** Everything rendered in the UI is derived from real backend events (`UNKNOWN` if absent).
* **Vision vs Screenshot Distinction:** The Observatory displays `SCREENSHOT_CAPTURED` distinctly from `VISION_INFERENCE`. If DOM grounding resolves the target field without vision, it displays `VISION_REQUIRED=false`.
* **Zero Chain-of-Thought Leaks:** Displays only structured summaries and safe metadata.
* **Credential Redaction:** Passwords, tokens, cookies, auth headers, and API keys are stripped automatically before broadcasting.

---

## 3. Event Schema

Every event emitted from Pilot Core complies with the standardized schema:

```json
{
  "event_id": "104",
  "run_id": "c21b37fd-811c-4613-8cfb-...",
  "task_id": "c21b37fd-811c-4613-8cfb-...",
  "timestamp": "2026-09-11T06:12:00.000Z",
  "event_type": "MODEL_SELECTED",
  "status": "running",
  "step_index": 0,
  "message": "Selected model qwen2.5:1.5b for role planner",
  "metadata": {
    "planner_model": "qwen2.5:1.5b",
    "vision_model": "qwen3-vl:2b",
    "fallback_model": "moondream:latest",
    "reason": "Structured intent & planning"
  }
}
```

### Standard Event Lifecycle:
1. `TASK_STARTED`
2. `MODEL_SELECTED`
3. `PLAN_CREATED`
4. `NAVIGATION_STARTED`
5. `NAVIGATION_SUCCEEDED`
6. `PAGE_READY`
7. `SCREENSHOT_CAPTURED`
8. `DOM_OBSERVED`
9. `VISION_STARTED` *(only if vision model actually called)*
10. `VISION_COMPLETED` *(only if vision model actually called)*
11. `DECISION_MADE` *(with source: DOM, VISION, or DOM + VISION)*
12. `ACTION_STARTED`
13. `ACTION_SUCCEEDED` / `ACTION_FAILED`
14. `VERIFICATION_STARTED`
15. `VERIFICATION_PASSED`
16. `TASK_COMPLETED`

---

## 4. How to Run

### Method 1: Start Observatory Only
When Pilot Core is already running:
```bash
start_observatory.bat
```
Or manually:
```bash
# Terminal 1 - Observatory Backend (:8766)
python -m observatory.backend.main

# Terminal 2 - Observatory Frontend (:3001)
cd observatory/frontend
npm run dev -- --port 3001
```

### Method 2: Start All Services Together
```bash
start_all.bat
```
Or with Python:
```bash
python main.py --observatory
```

Open:
* **Observatory:** `http://127.0.0.1:3001`
* **Pilot:** `http://127.0.0.1:1420`
