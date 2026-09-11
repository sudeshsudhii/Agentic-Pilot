# Pilot Agent Observatory

The **Pilot Agent Observatory** is a standalone, real-time developer dashboard engineered to provide complete visual introspection into the internal decision-making, model routing, DOM interactions, and verification steps of Agentic Pilot.

---

## Architectural Isolation

To ensure that real-time telemetry rendering never degrades agent latency or execution memory, the Observatory runs as an independent application and process on separate ports:

```mermaid
flowchart LR
    subgraph ExecutionCore ["Execution Domain (:8765)"]
        PILOT["Pilot Core Backend<br/>(FastAPI / LangGraph)"]
    end

    subgraph ObservatoryDomain ["Observatory Telemetry Domain"]
        OBS_BACKEND["Observatory Backend (:8766)<br/>(FastAPI / Event Stream Hub)"]
        OBS_FRONTEND["Observatory Frontend (:3001)<br/>(React / Vite SPA)"]
    end

    PILOT -->|Internal Event Bus / SSE<br/>Zero-blocking dispatch| OBS_BACKEND
    OBS_BACKEND -->|Direct WebSocket /ws<br/>Keepalive Ping/Pong| OBS_FRONTEND
    OBS_FRONTEND -->|HTTP REST /api/*<br/>Run History & Performance| OBS_BACKEND

    classDef execStyle fill:#0f172a,stroke:#38bdf8,stroke-width:1.5px,color:#f8fafc;
    classDef obsStyle fill:#1e1b4b,stroke:#a855f7,stroke-width:1.5px,color:#f8fafc;
    class PILOT execStyle;
    class OBS_BACKEND,OBS_FRONTEND obsStyle;
```

---

## Core Dashboard Views & Components

The Observatory frontend (`observatory/frontend/src/App.tsx`) is structured into four primary functional views:

```mermaid
flowchart TD
    TABS["Observatory Navigation Tabs"] --> TAB1["1. Live Observatory"]
    TABS --> TAB2["2. Run History View"]
    TABS --> TAB3["3. Experience View"]
    TABS --> TAB4["4. LangGraph State View"]

    subgraph LiveComponents ["Live Observatory Telemetry Suite"]
        P_ALERT["Blocked Alert Banner<br/>(CAPTCHA / Human Approval)"]
        P_ROUTER["Model & Dynamic Router Panel<br/>(Active model, tier, reason, invocation count)"]
        P_PLAN["Task Plan & Progress Panel<br/>(Subgoals, completion checkboxes)"]
        P_OBS["Browser Observation Proof<br/>(Live screenshot, URL, DOM state)"]
        P_VISION["Vision Observability Panel<br/>(Coordinate bounding box, VLM status)"]
        P_ACTION["Decision & Action Panel<br/>(Current action, selector, duration)"]
        P_VERIFY["Verification Panel<br/>(Expected vs Observed, Confidence)"]
        P_PERF["Performance Panel<br/>(Latency breakdown by subsystem)"]
        P_TRACE["Timeline Trace<br/>(Chronological event log with filter & JSON inspector)"]
    end

    TAB1 --> LiveComponents
```

---

## View Breakdown

### 1. Live Observatory
* **Model & Dynamic Router**: Displays the primary reasoning LLM (`qwen2.5:1.5b`), active vision model (`moondream`), routing policy (`reasoning`, `fast`, `balanced`), and routing rationale (e.g., *"Fallback to configured model_fallback 'qwen2.5:1.5b'"*).
* **Task Plan & Progress**: Shows the high-level goal, step counter, and subtask decomposition.
* **Browser Observation Proof**: Displays the real-time screenshot captured after the most recent navigation or action.
* **Vision Observability**: Displays normalized coordinates (`x_percent`, `y_percent`), pixel calculations, and whether the vision model or DOM selector was utilized.
* **Decision & Action Panel**: Summarizes the current action type, targeted element locator, action execution latency, and prior action history.
* **Verification Panel**: Highlights the hard verification record with color-coded PASS (green) / FAIL (rose) badges, comparing `expected` vs `observed` data dictionaries.
* **Performance Panel**: Live bar charts displaying latency distribution across Planner, Vision, Browser Action, Verification, and Waiting tiers.
* **Timeline Trace**: A searchable, chronological log of all emitted telemetry events (`TASK_STARTED`, `DOM_EXTRACTED`, `ACTION_PLANNED`, `VERIFICATION_RECORDED`).

### 2. Run History View
* Queries SQLite (`pilot.db`) to display historical agent execution sessions.
* Filters by status (`completed`, `failed`, `blocked`), task duration, and timestamp.
* Clicking any historical run loads its full event trace, screenshot proofs, and performance metrics into the Live Observatory interface for replay inspection.

### 3. Experience View
* Interfaces with ChromaDB (`pilot_memories`) and SQLite to display episodic memories accumulated by the agent.
* Inspects successful strategies, failure diagnoses, and domain-specific knowledge tags that the agent re-uses across tasks.

### 4. LangGraph State View
* A developer inspection utility providing a real-time JSON dump of the underlying `AgentState` object.
* Displays raw internal state variables, including `action_manifest`, `retrieved_knowledge`, `approval_id`, and `retry_count`.

---

## Telemetry Event Model

Events dispatched from the core backend implement the `ObservatoryEvent` schema:

```typescript
interface ObservatoryEvent {
  event_id: string;
  run_id: string;
  task_id: string;
  timestamp: string;
  event_type: string;     // e.g. "TASK_STARTED", "ACTION_EXECUTED", "VERIFICATION_RECORDED"
  status: string;         // "running", "completed", "failed", "blocked"
  step_index: number;
  message: string;
  metadata: Record<string, any>;
}
```

---

*Related Pages:*
* [[Evidence & Verification|Evidence-and-Verification]]
* [[Architecture|Architecture]]
* [[Experience & Learning|Experience-and-Learning]]
