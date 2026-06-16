# Execution Flow Documentation

Agentic Pilot operates via a strict state machine orchestrating Playwright automation, LLM planning, and evidence capture.

## State Machine Pipeline (`backend/agent/graph.py`)

1. **`parse_intent_node`**:
   - Prompts the LLM to structure the query.
   - If parsing fails, routes directly to `error_recovery` (no heuristic fallbacks).
2. **`risk_check_node`**:
   - Pauses execution and transitions to `waiting_approval` if risk level is high.
3. **`navigate_node`**:
   - Directs Playwright to the destination URL.
   - Executes hard verification on the URL.
4. **`extract_dom_node`**:
   - Compresses the Playwright active page into a 50-element DOM Action Manifest.
5. **`plan_action_node`**:
   - Queries `qwen2.5` to plan the next element interaction based on the current DOM.
   - Falls back to `qwen2.5-vl` (Vision) if standard DOM interactions fail.
6. **`execute_action_node`**:
   - **Pre-execution:** Calls `EvidenceManager` to capture `before.png` and `dom_snapshot.json`.
   - Executes the action via Playwright.
   - **Post-execution:** Captures `after.png` and saves Playwright assertion state to `verification.json`.
7. **`verify_node`**:
   - If Playwright or Verification fails, evaluates retry counter. If exhausted, task is `FAILED`.
   - If action is `complete`, task is `COMPLETED`.

## Evidence Pipeline
All artifacts are saved to `~/.pilot/evidence/{task_id}/`. The UI and external consumers can leverage these files for detailed research audits.
