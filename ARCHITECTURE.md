# Agentic Pilot Architecture

## Core Philosophy
Agentic Pilot strictly enforces physical execution validation. The state machine operates on the principle: **No claim without execution. No completion without verification.**

## Components

### 1. LangGraph State Machine
`backend/agent/graph.py` orchestrates execution.
- `parse_intent`: Structures the request and assesses risk.
- `navigate_node`: Directs the executor.
- `extract_dom`: Compresses the Playwright page state into a 50-element manifest.
- `plan_action`: Evaluates DOM vs Intent using Ollama (Qwen2.5-Coder).
- `execute_action`: Triggers `PlaywrightExecutor`.
- `verify_node`: Verifies execution constraints via `VerificationManager`.
- `error_recovery`: Manages retries via `RecoveryEngine`.

### 2. Execution Layer
`PlaywrightExecutor` directly controls browser contexts. It never simulates success. If an element cannot be clicked, it throws a `VerificationError`.

### 3. Verification Framework
`VerificationManager` sits between Execution and Planning.
It validates:
- `verify_url`: Catches DNS, Chrome error pages, and 404s.
- `verify_dom_mutation`: Detects click states.
- `verify_input_value`: Asserts typed text explicitly against Playwright's `input_value()`.

### 4. Memory & Vision Providers
- `MemoryProvider`: Abstracted vector DB (Chroma) for semantic state retrieval.
- `VisionProvider`: Abstracted Vision-Language Model fallback (Qwen2.5-VL) for complex visual grounding.

### 5. Evidence & Replay
All tasks generate an immutable `~/.pilot/evidence/` record containing `before.png`, `after.png`, `trace.json`, `dom_snapshot.json`, and `telemetry.json`. `ReplaySystem` allows full task reconstruction for debugging.
