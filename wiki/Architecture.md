# System Architecture

The architecture of **Agentic Pilot** is designed around strict principles of local data sovereignty, separation of concerns, and resilient closed-loop state transitions. The system operates as a distributed set of decoupled processes communicating over localhost network interfaces.

---

## High-Level Topology & Port Mapping

Agentic Pilot separates operational execution from administrative observation to guarantee that telemetry collection and developer inspection never interfere with real-time agent decision-making.

```mermaid
flowchart TB
    subgraph Ports ["Local Port Allocation"]
        P1420["Port 1420<br/>Pilot User Frontend<br/>(Tauri / Web UI)"]
        P3001["Port 3001<br/>Pilot Agent Observatory<br/>(React / Vite UI)"]
        P8765["Port 8765<br/>Pilot Core Backend<br/>(FastAPI / LangGraph)"]
        P8766["Port 8766<br/>Observatory Telemetry Backend<br/>(FastAPI / Event Hub)"]
        P11434["Port 11434<br/>Ollama Inference Engine<br/>(Local LLM / VLM API)"]
    end

    P1420 -->|HTTP REST / WebSocket<br/>Task Dispatch & Approvals| P8765
    P8765 -->|HTTP JSON-RPC<br/>Prompt & Vision Inference| P11434
    P8765 -->|Event Stream SSE / Internal Bus<br/>JSON Telemetry Events| P8766
    P3001 -->|WebSocket /ws<br/>Bi-directional Real-time Feed| P8766
    P3001 -->|HTTP REST /api/*<br/>Run History & Metrics| P8766

    classDef portStyle fill:#1e293b,stroke:#38bdf8,stroke-width:2px,color:#f8fafc;
    class P1420,P3001,P8765,P8766,P11434 portStyle;
```

---

## Detailed Component Architecture

```mermaid
flowchart LR
    subgraph CoreBackend ["Pilot Core Backend (:8765)"]
        API["FastAPI App<br/>(backend/main.py)"]
        
        subgraph GraphEngine ["LangGraph Execution Engine"]
            GRAPH["StateGraph<br/>(backend/agent/graph.py)"]
            STATE["AgentState TypedDict<br/>(backend/agent/state.py)"]
            NODES["11 Execution Nodes<br/>(backend/agent/nodes.py)"]
        end

        subgraph Subsystems ["Core Subsystems"]
            ROUTER["ModelRouter & Registry<br/>(backend/llm/router.py)"]
            VERIFY["VerificationManager<br/>(backend/verification/manager.py)"]
            RECOVER["RecoveryEngine<br/>(backend/recovery/engine.py)"]
            DOM_EXT["DOMExtractor<br/>(backend/browser/dom.py)"]
            ACT_EXEC["ActionExecutor<br/>(backend/browser/actions.py)"]
            MEM_PROV["ChromaProvider<br/>(backend/memory/provider.py)"]
        end

        subgraph StorageLayer ["Persistence"]
            SQLITE[("SQLite Database<br/>pilot.db")]
            CHROMA[("ChromaDB Vector Store<br/>.data/chroma")]
        end
    end

    subgraph BrowserProcess ["Browser Automation"]
        PLAYWRIGHT["Playwright Async Core<br/>(Chromium Sandbox)"]
    end

    subgraph InferenceHost ["Local LLM Host (:11434)"]
        OLLAMA_SRV["Ollama Daemon"]
    end

    API --> GRAPH
    GRAPH --- STATE
    GRAPH --> NODES
    NODES --> ROUTER
    NODES --> VERIFY
    NODES --> RECOVER
    NODES --> ACT_EXEC
    NODES --> DOM_EXT
    NODES --> MEM_PROV

    ROUTER -->|HTTP API| OLLAMA_SRV
    ACT_EXEC -->|DevTools Protocol| PLAYWRIGHT
    DOM_EXT -->|CDP / DOM Scripts| PLAYWRIGHT
    MEM_PROV --> CHROMA
    NODES --> SQLITE
```

---

## Architectural Layers

### 1. Client & Presentation Layer
* **Pilot User UI (`:1420`)**: User-facing application for entering prompts, monitoring task progress, granting human-in-the-loop approvals, and viewing final outputs.
* **Pilot Agent Observatory (`:3001`)**: Read-only engineering dashboard that consumes real-time telemetry events. Displays model routing decisions, planned subgoals, visual coordinate bounding boxes, verification proofs, and LangGraph state variables.

### 2. Orchestration & Graph Layer (`backend/agent`)
* **LangGraph `StateGraph`**: A compiled cyclic graph defining 11 deterministic states. Unlike linear ReAct chains, LangGraph allows conditional routing, looping back to re-observe the DOM upon failed actions, and structured recovery escalation.
* **`AgentState`**: A strongly-typed Python dictionary (`TypedDict`) containing task inputs, parsed goals, active model, locator trees, action histories, verification records, and recovery flags.
* **Nodes & Routers**: Modular functions executing atomic phases (`parse_intent_node`, `navigate_node`, `plan_action_node`, `execute_action_node`, `verify_node`, `error_recovery_node`).

### 3. Cognition & Routing Layer (`backend/llm`)
* **`ModelRegistry`**: Maintains operational metadata for installed Ollama models (context length, latency tier, priority, capabilities).
* **`CapabilityAnalyzer`**: Parses incoming subtasks to deduce required capabilities (`planning`, `coding`, `vision`, `lightweight`, `recovery`).
* **`ModelRouter`**: Dynamically maps task demands to the best local model while preventing model switching thrashing.

### 4. Perception & Action Layer (`backend/browser` & `backend/vision`)
* **`ActionExecutor`**: Executes actions against the active Playwright `Page` (`click`, `type_text`, `select_option`, `navigate`, `scroll`).
* **`DOMExtractor`**: Parses the webpage into an accessibility-focused interactive tree, pruning invisible elements and assigning numerical element IDs.
* **`VisionFallback`**: Activated when DOM selectors are insufficient or dynamic canvas/iframe elements are present. Uses multimodal VLMs to infer normalized `(x, y)` coordinates.

### 5. Verification & Recovery Layer (`backend/verification` & `backend/recovery`)
* **`VerificationManager`**: Performs post-action deterministic checks (URL navigation status, DOM mutation delta, form input value confirmation).
* **`RecoveryEngine`**: Classifies failures into discrete error types (`captcha`, `transient`, `element_not_found`, `verification_failed`) and enforces a four-tier escalation ladder.

### 6. Persistence & Memory Layer (`backend/db` & `backend/memory`)
* **SQLite (`pilot.db`)**: Stores runs, tasks, action steps, verification events, and operational audits.
* **ChromaDB (`.data/chroma`)**: Vector database powering semantic retrieval of past task strategies, successes, and failure diagnoses.

---

## Data Flow Pipeline

```mermaid
sequenceDiagram
    autonumber
    actor User as User
    participant UI as Pilot Frontend (:1420)
    participant Core as Pilot Core (:8765)
    participant Ollama as Ollama Server (:11434)
    participant Browser as Playwright Browser
    participant Obs as Observatory (:8766/:3001)

    User->>UI: Submit task ("Search for flight prices")
    UI->>Core: POST /api/tasks (input_text)
    Core->>Obs: Emit Event: TASK_STARTED

    Core->>Ollama: POST /api/generate (Parse Intent & Task Plan)
    Ollama-->>Core: JSON Intent & Subgoal Array
    Core->>Obs: Emit Event: MODEL_INFERRED & PLAN_UPDATED

    Core->>Browser: page.goto(target_url)
    Browser-->>Core: Navigation Complete
    Core->>Browser: Extract DOM Tree & Capture Screenshot
    Browser-->>Core: DOM JSON + Screenshot Bytes
    Core->>Obs: Emit Event: DOM_EXTRACTED & SCREENSHOT_CAPTURED

    Core->>Ollama: POST /api/generate (Select Action based on DOM)
    Ollama-->>Core: PlannedAction (click, selector: "#search-btn")
    Core->>Obs: Emit Event: ACTION_PLANNED

    Core->>Browser: Execute Action (click element)
    Browser-->>Core: ActionResult (DOM Mutated)

    Core->>Browser: Verification Check (inspect new DOM & URL)
    Browser-->>Core: Verified: True
    Core->>Obs: Emit Event: VERIFICATION_RECORDED (PASS)

    Core->>UI: Final Answer & Task Completed
    Core->>Obs: Emit Event: TASK_COMPLETED
```

---

*Related Pages:*
* [[Agent Execution Lifecycle|Agent-Execution-Lifecycle]]
* [[Local LLM & Model Routing|Local-LLM-and-Model-Routing]]
* [[Agent Observatory|Agent-Observatory]]
