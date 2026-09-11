# Agentic Pilot — Configuration Guide

Agentic Pilot is configured using environment variables, an optional `.env` file, or defaults defined in `backend/config.py`. All environment variables use the `PILOT_` prefix.

---

## 1. Core Model & Ollama Settings

| Variable | Type | Default | Description |
|---|---|---|---|
| `PILOT_OLLAMA_BASE_URL` | String | `http://127.0.0.1:11434` | HTTP URL of the local Ollama daemon. |
| `PILOT_OLLAMA_MODEL` | String | `qwen2.5:1.5b` | Default general-purpose model. |
| `PILOT_OLLAMA_VISION_MODEL` | String | `moondream` | Default visual grounding model. |
| `PILOT_MODEL_ROUTING_STRATEGY` | String | `dynamic` | Routing policy: `dynamic` (role-based), `static`, or `single`. |
| `PILOT_MODEL_REASONING` | String | `qwen2.5:7b` | Model assigned to the `planner` and `recovery` roles. |
| `PILOT_MODEL_CODING` | String | `qwen2.5-coder:3b` | Model assigned to code generation and script tasks. |
| `PILOT_MODEL_LIGHTWEIGHT` | String | `deepseek-r1:1.5b` | Model assigned to rapid intent classification. |
| `PILOT_MODEL_FALLBACK` | String | `qwen2.5:1.5b` | Model invoked when a specialized candidate is offline. |
| `PILOT_MODEL_SWITCH_COOLDOWN_STEPS` | Integer | `1` | Minimum steps before switching models to prevent thrashing. |

---

## 2. Browser Automation Settings

| Variable | Type | Default | Description |
|---|---|---|---|
| `PILOT_HEADLESS_BROWSER` | Boolean | `false` | When `false`, Chromium launches visibly for real-time observation. |
| `PILOT_BROWSER_POOL_SIZE` | Integer | `3` | Maximum concurrent browser contexts in the execution pool. |
| `PILOT_KEEP_BROWSER_OPEN` | Boolean | `true` | Retains browser open after task completion for human inspection. |
| `PILOT_BROWSER_IDLE_TIMEOUT_MINUTES`| Integer | `15` | Idle timeout before cleaning up retained browser sessions. |

---

## 3. Execution & Safety Configuration

| Variable | Type | Default | Description |
|---|---|---|---|
| `PILOT_SERVER_PORT` | Integer | `8765` | Pilot backend HTTP/WebSocket port. |
| `PILOT_AUTO_APPROVE_LOW_RISK` | Boolean | `true` | Automatically approve read-only and navigation actions. |
| `PILOT_APPROVAL_TIMEOUT_SECONDS` | Integer | `10` | Timeout before unapproved high-risk tasks pause or abort. |
| `PILOT_MAX_RETRY_COUNT` | Integer | `3` | Maximum recovery attempts per action before failing. |
| `PILOT_MAX_TASK_DURATION_MINUTES` | Integer | `5` | Maximum execution window before task timeout. |

---

## 4. Research & Ablation Flags

Agentic Pilot provides feature flags to disable specific subsystems for comparative benchmark research:

| Flag | Default | When Disabled (`false`) |
|---|---|---|
| `PILOT_ENABLE_EVIDENCE` | `true` | Skips screenshot and DOM artifact persistence to disk. |
| `PILOT_ENABLE_VERIFICATION` | `true` | Disables post-action Expected vs Observed verification (blind execution). |
| `PILOT_ENABLE_RECOVERY` | `true` | Disables recovery loops; any failure immediately terminates the task. |
| `PILOT_ENABLE_MEMORY` | `true` | Disables episodic memory retrieval of previous strategies. |
| `PILOT_ENABLE_RAG` | `true` | Disables retrieval of external knowledge documents. |
| `PILOT_ENABLE_MULTI_MODEL` | `true` | Locks all operations to the single default model. |

---

## 5. Storage & Privacy Audit

| Variable | Type | Default | Description |
|---|---|---|---|
| `PILOT_DB_PATH` | String | `~/.pilot/data.db` | Path to local SQLite database for tasks and event logs. |
| `PILOT_DATA_DIR` | String | `~/.pilot/data` | Root directory for evidence, screenshots, and logs. |
| `PILOT_PRIVACY_AUDIT_ENABLED` | Boolean | `true` | Logs all outbound traffic and token sizes to verify zero exfiltration. |
| `PILOT_PRIVACY_AUDIT_LOG` | String | `~/.pilot/logs/privacy_audit.jsonl` | Append-only privacy audit log file. |
