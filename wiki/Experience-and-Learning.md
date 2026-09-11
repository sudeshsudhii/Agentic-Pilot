# Experience & Episodic Learning

Agentic Pilot features a dual-tier memory system designed to retain knowledge across autonomous executions. By learning which selectors, workflows, and navigation paths succeed or fail on specific web domains, the agent avoids repeating costly trial-and-error mistakes.

---

## Dual-Tier Memory Architecture

The memory system combines relational metadata tracking in **SQLite** with dense semantic vector indexing in **ChromaDB**:

```mermaid
flowchart TD
    subgraph ExecutionDomain ["Agent Execution Loop"]
        RETRIEVE_NODE["retrieve_context_node<br/>(Query prior task experiences)"]
        COMPLETE_NODE["complete_node<br/>(Persist outcome & diagnosis)"]
    end

    subgraph MemoryTier ["Dual-Tier Memory Manager (ChromaProvider)"]
        CHROMA_CLIENT["ChromaDB Persistent Client<br/>(.data/chroma)"]
        SQLITE_CLIENT["SQLite Database<br/>(pilot.db: memories table)"]
    end

    RETRIEVE_NODE -->|Semantic Query Vector| CHROMA_CLIENT
    CHROMA_CLIENT -->|Top-K Memory IDs| SQLITE_CLIENT
    SQLITE_CLIENT -->|Hydrated MemoryRecord Array| RETRIEVE_NODE

    COMPLETE_NODE -->|Store Strategy / Failure| CHROMA_CLIENT
    COMPLETE_NODE -->|Insert Metadata & Tags| SQLITE_CLIENT

    classDef execStyle fill:#0f172a,stroke:#38bdf8,stroke-width:1.5px,color:#f8fafc;
    classDef memStyle fill:#1e1b4b,stroke:#a855f7,stroke-width:1.5px,color:#f8fafc;
    class RETRIEVE_NODE,COMPLETE_NODE execStyle;
    class CHROMA_CLIENT,SQLITE_CLIENT memStyle;
```

---

## Memory Record Schema

Every stored memory adheres to the `MemoryRecord` model (`backend/memory/provider.py`):

```python
class MemoryRecord(BaseModel):
    memory_id: str                      # Unique UUID v4
    type: str                           # "semantic", "strategy", "failure", "episodic"
    content: str                        # Natural language distillation of the experience
    task_id: str | None = None          # Associated task session identifier
    tags: list[str] = []                # Domain or technology tags (e.g. ["google.com", "flight_search"])
    created_at: str                     # ISO 8601 UTC timestamp
    last_accessed_at: str               # ISO 8601 UTC timestamp
    access_count: int                   # Frequency of reuse
```

---

## Core Memory Operations

### 1. Context Retrieval (`retrieve_relevant` & `retrieve_strategies`)
* **Trigger**: Invoked automatically during `retrieve_context_node` before action planning.
* **Mechanism**: Generates vector embeddings for the current task prompt and domain, querying the `pilot_memories` collection for the top-$K$ most relevant records.
* **Injection**: Injected into the prompt sent to the local reasoning LLM as structured guidance:
  ```markdown
  ### Retrieved Past Experiences
  - [SUCCESS]: On domain example.com, submit button requires scrolling into view before click.
  - [FAILURE]: Selector '#old-login' fails due to dynamic iframe; use visual fallback instead.
  ```

### 2. Strategy Storage (`store_strategy`)
* **Trigger**: Invoked by `complete_node` when a task successfully accomplishes its goal.
* **Content**: Stores an abstracted summary of the sequence of actions that proved effective.

### 3. Failure Learning (`store_failure`)
* **Trigger**: Invoked by `complete_node` or `error_recovery_node` when an action or verification fails.
* **Content**: Records the failed selector, the error diagnostic, and the recovery strategy that resolved it.

---

## The Experience Lifecycle

```mermaid
sequenceDiagram
    autonumber
    participant Task as Active Task
    participant Node as retrieve_context_node
    participant Chroma as ChromaDB (.data/chroma)
    participant Planner as plan_action_node
    participant Comp as complete_node

    Task->>Node: Current URL & Step Goal
    Node->>Chroma: query_texts(["Search input on flight booking"])
    Chroma-->>Node: Top-3 Matching MemoryRecords
    Node->>Planner: Injected Memories into Prompt State
    Planner->>Task: Avoid Known Pitfalls / Select Optimal Action
    Task->>Comp: Task Completed Successfully
    Comp->>Chroma: store_strategy(goal, successful_actions)
    Chroma-->>Comp: Memory Saved for Future Runs
```

---

*Related Pages:*
* [[Agent Execution Lifecycle|Agent-Execution-Lifecycle]]
* [[Agent Observatory|Agent-Observatory]]
* [[CAPTCHA & Failure Recovery|CAPTCHA-and-Failure-Recovery]]
