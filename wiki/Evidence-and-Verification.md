# Evidence & Hard Verification

A foundational defect in standard LLM agent frameworks is "hallucinated completion"—where an agent assumes an action succeeded simply because the LLM generated the tool call. **Agentic Pilot** solves this by enforcing an **Evidence-Driven Hard Verification Framework** (`backend/verification/manager.py`).

---

## Verification Pipeline: Expected → Observed → Proof

Every browser action executed by the agent must pass an independent deterministic post-condition verification check before the task is allowed to proceed or conclude.

```mermaid
flowchart TD
    ACTION["Action Executed by Playwright<br/>(click, type_text, navigate)"] --> RECORD["Capture Post-Action State<br/>(current_url, DOM html, screenshot, input values)"]
    
    RECORD --> VM["VerificationManager Assessment"]

    subgraph VerificationChecks ["Deterministic Verification Suite"]
        C1["URL Verification<br/>(Verify navigation succeeded, not chrome-error://)"]
        C2["DOM Mutation Check<br/>(Compute DOM diff; ensure state reacted)"]
        C3["Input Value Confirmation<br/>(Inspect input.value === expected_text)"]
        C4["Visual Proof Capture<br/>(Screenshot hash & element bounding box)"]
    end

    VM --> C1
    VM --> C2
    VM --> C3
    VM --> C4

    C1 --> EVAL{"All Post-Conditions Met?"}
    C2 --> EVAL
    C3 --> EVAL
    C4 --> EVAL

    EVAL -->|Yes| PASS["Emit VerificationResult: PASS<br/>confidence = 1.0"]
    EVAL -->|No| FAIL["Emit VerificationResult: FAIL<br/>Raise VerificationError"]

    PASS --> ADVANCE["Advance LangGraph to Next Subgoal"]
    FAIL --> ESCALATE["Route to error_recovery_node<br/>(Escalate Strategy)"]

    classDef checkStyle fill:#0f172a,stroke:#38bdf8,stroke-width:1.5px,color:#f8fafc;
    classDef passStyle fill:#064e3b,stroke:#10b981,stroke-width:1.5px,color:#ecfdf5;
    classDef failStyle fill:#7f1d1d,stroke:#f43f5e,stroke-width:1.5px,color:#fff1f2;
    class C1,C2,C3,C4 checkStyle;
    class PASS,ADVANCE passStyle;
    class FAIL,ESCALATE failStyle;
```

---

## The `VerificationResult` Schema

Verification events produce a structured `VerificationResult` record that enables precise ablation benchmarking and auditing:

```python
class VerificationResult(BaseModel):
    verified: bool                      # True if check succeeded, False if failed
    type: str                           # "url", "dom_mutation", "text_typed", "state_assertion"
    expected: dict[str, Any]            # What the action intended to cause
    observed: dict[str, Any]            # What the browser DOM/URL actually reflects
    confidence: float                   # Verification confidence score (0.0 to 1.0)
    message: str                        # Diagnostic explanation
    timestamp: str                      # ISO 8601 UTC timestamp
```

### Example Verification Evidence Payloads

#### 1. Navigation Verification
```json
{
  "verified": true,
  "type": "url",
  "expected": { "requested_url": "https://example.com/login" },
  "observed": { "current_url": "https://example.com/login", "status": 200 },
  "confidence": 1.0,
  "message": "URL successfully reached without browser network error"
}
```

#### 2. Form Input Typing Verification
```json
{
  "verified": true,
  "type": "text_typed",
  "expected": { "target_input": "search-input", "value": "Agentic Pilot" },
  "observed": { "element_value": "Agentic Pilot", "matches": true },
  "confidence": 1.0,
  "message": "Element value strictly matches requested text"
}
```

---

## Core Verification Routines

### 1. Navigation Verification (`verify_url`)
* **Checks**: Confirms the page URL loaded cleanly.
* **Failure Detection**: Flags browser error protocols (`chrome-error://`), DNS lookup failures (`ERR_NAME_NOT_RESOLVED`), and connection timeouts (`ERR_CONNECTION_REFUSED`).

### 2. DOM Mutation Verification (`verify_dom_mutation`)
* **Checks**: Compares the HTML snapshot before and after an interaction.
* **Failure Detection**: Detects dead clicks (clicks on unclickable canvas overlays or dead anchors) where the underlying DOM tree underwent zero modification.

### 3. Exact Text Verification (`extract_exact_text_to_type`)
* **Checks**: Uses regex intent extractors to isolate requested quotes, then inspects the active DOM input element's `.value` property.
* **Failure Detection**: Flags incomplete typing (e.g., typing cut off by keyup listeners or character limit truncations).

### 4. Visual Evidence Collection
* **Checks**: Takes a timestamped screenshot after every major state transition.
* **Storage**: Encoded into the telemetry event stream and saved to disk for post-run visual auditing in the **Agent Observatory**.

---

*Related Pages:*
* [[Browser Automation|Browser-Automation]]
* [[Agent Execution Lifecycle|Agent-Execution-Lifecycle]]
* [[Agent Observatory|Agent-Observatory]]
