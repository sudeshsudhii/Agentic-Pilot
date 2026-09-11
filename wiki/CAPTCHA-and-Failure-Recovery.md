# CAPTCHA & Failure Recovery

Web automation in adversarial environments is subject to anti-bot challenges, transient network drops, dynamic DOM changes, and unexpected modal overlays. **Agentic Pilot** replaces naive retry loops with an intelligent, multi-stage **Recovery Engine** (`backend/recovery/engine.py`).

---

## Strategy Escalation Ladder

When an action or verification check fails, the `RecoveryEngine` routes the agent through a bounded four-tier escalation ladder:

```mermaid
flowchart TD
    FAILURE["Execution or Verification Failure"] --> CLASSIFY["1. Failure Classification<br/>(Analyze error message against patterns)"]
    CLASSIFY --> DIAGNOSE["2. Failure Diagnosis<br/>(Generate human-readable explanation)"]
    
    DIAGNOSE --> CHECK_CAPTCHA{"Is Failure a CAPTCHA / Bot Block?"}
    CHECK_CAPTCHA -->|Yes| BLOCKED["Status: 'blocked'<br/>Notify Human in the Loop"]
    
    CHECK_CAPTCHA -->|No| CHECK_BUDGET{"Retries Exhausted?<br/>(retry_count >= max_retries)"}
    CHECK_BUDGET -->|Yes| EXHAUSTED["Status: 'exhausted'<br/>Graceful Failure Termination"]

    CHECK_BUDGET -->|Retries Available| LADDER["3. Strategy Escalation Ladder"]

    subgraph EscalationLadder ["Strategy Levels"]
        L1["Level 1: retry<br/>(Re-execute same action & locator)"]
        L2["Level 2: alternative_selector<br/>(Try secondary ID, text, or CSS selector)"]
        L3["Level 3: vision_fallback<br/>(Bypass DOM; visually locate element with VLM)"]
        L4["Level 4: replan<br/>(Ask reasoning LLM for alternate navigation route)"]
    end

    LADDER --> L1
    L1 -->|Fails Again| L2
    L2 -->|Fails Again| L3
    L3 -->|Fails Again| L4

    L1 --> EXEC["Loop back to extract_dom_node"]
    L2 --> EXEC
    L3 --> EXEC
    L4 --> EXEC

    classDef procStyle fill:#0f172a,stroke:#38bdf8,stroke-width:1.5px,color:#f8fafc;
    classDef checkStyle fill:#1e1b4b,stroke:#a855f7,stroke-width:1.5px,color:#f8fafc;
    classDef termStyle fill:#7f1d1d,stroke:#f43f5e,stroke-width:1.5px,color:#fff1f2;
    class CLASSIFY,DIAGNOSE,LADDER,L1,L2,L3,L4,EXEC procStyle;
    class CHECK_CAPTCHA,CHECK_BUDGET checkStyle;
    class BLOCKED,EXHAUSTED termStyle;
```

---

## Failure Classification Hierarchy

The `RecoveryEngine` categorizes raw runtime exceptions into discrete failure classes:

| Failure Type | Recognized Signatures | Default Escalation Policy |
| :--- | :--- | :--- |
| `captcha` | `captcha`, `recaptcha`, `sorry/index`, `unusual traffic`, `bot verification`, `i'm not a robot` | **Immediate Halt (`blocked`)**. Do not retry to prevent IP bans. Request human intervention. |
| `transient` | `timeout`, `net::ERR_`, `CONNECTION_REFUSED`, `socket hung up` | Level 1: `retry` with exponential backoff. |
| `element_not_found`| `Element has no usable selector`, `missing element`, `element not found` | Level 2: `alternative_selector` → Level 3: `vision_fallback`. |
| `verification_failed` | `Verification failed`, `Input verification failed`, `URL mismatch` | Level 2: `alternative_selector` → Level 4: `replan`. |
| `navigation_failed` | `DNS lookup failed`, `chrome-error://`, `HTTP 5xx` | Level 1: `retry` → Level 4: `replan`. |
| `vision_needed` | `need_help`, `Cannot find element in DOM tree` | Level 3: `vision_fallback`. |
| `llm_failure` | `Structured LLM response failed`, `not valid JSON` | Level 1: `retry` with increased JSON temperature constraints. |

---

## Human-in-the-Loop Intervention

When a CAPTCHA or anti-bot challenge is detected:

```mermaid
sequenceDiagram
    autonumber
    participant Agent as Agent Execution Node
    participant Rec as RecoveryEngine
    participant Obs as Agent Observatory (:3001)
    actor Human as Human Operator
    participant Core as Pilot Core Backend (:8765)

    Agent->>Rec: Error: "unusual traffic / captcha detected"
    Rec->>Agent: Strategy: "blocked"
    Agent->>Core: Update AgentState (status="blocked", approval_id=UUID)
    Core->>Obs: Emit Event: BLOCKED_ALERT
    Obs-->>Human: Visual Alert: CAPTCHA Detected on Target Page
    Human->>Agent: Solves CAPTCHA in Headful Browser / Grants Approval
    Human->>Obs: Click "Approve / Resume Execution"
    Obs->>Core: POST /api/approvals/{approval_id}
    Core->>Agent: Reset Retry Count & Resume StateGraph
```

### Safety Guarantees
1. **Zero Bot-Bypassing Hacks**: Agentic Pilot does not attempt brittle or unethical CAPTCHA-cracking services. It pauses cleanly and hands control to the operator.
2. **State Preservation**: The Playwright browser page and LangGraph memory state remain active during the block, allowing seamless resumption once resolved.

---

## Recovery Record Schema

Each recovery event is recorded as a `RecoveryRecord` (`backend/recovery/engine.py`):

```python
class RecoveryRecord(BaseModel):
    failure_type: str                   # Classified category
    diagnosis: str                      # Human-readable explanation
    strategy: str                       # Active escalation strategy
    retry_count: int                    # Current attempt index
    max_retries: int                    # Bounded limit (default: 6)
    outcome: str                        # "retry", "escalated", "exhausted"
    timestamp: str                      # ISO 8601 UTC timestamp
```

---

*Related Pages:*
* [[Vision System|Vision-System]]
* [[Evidence & Verification|Evidence-and-Verification]]
* [[Agent Execution Lifecycle|Agent-Execution-Lifecycle]]
