# Development Guide

This guide details how to extend, customize, and contribute to **Agentic Pilot**. The codebase follows modern Python 3.10+ async design patterns, type-annotated data models via **Pydantic**, and state machine choreography via **LangGraph**.

---

## Codebase Directory Structure

```text
pilot/
├── backend/                        # Pilot Core Backend Service (:8765)
│   ├── agent/                      # LangGraph StateGraph, nodes, and state models
│   │   ├── graph.py                # Graph compilation and edge router functions
│   │   ├── nodes.py                # Node implementations (11 atomic execution phases)
│   │   ├── state.py                # AgentState TypedDict specification
│   │   └── prompts.py              # System prompts for intent and action planning
│   ├── browser/                    # Playwright browser automation subsystem
│   │   ├── actions.py              # ActionExecutor (click, type_text, navigate)
│   │   ├── dom.py                  # DOMExtractor (accessibility tree parsing)
│   │   └── pool.py                 # BrowserPool lifecycle and context isolation
│   ├── llm/                        # Local LLM integration and dynamic routing
│   │   ├── router.py               # ModelRouter 4-stage pipeline
│   │   ├── registry.py             # ModelRegistry and ModelCapability definitions
│   │   ├── analyzer.py             # CapabilityAnalyzer requirement mapper
│   │   └── gateway.py              # OllamaGateway (JSON validation and schemas)
│   ├── vision/                     # Multimodal perception subsystem
│   │   └── fallback.py             # VisionFallback and coordinate grounding
│   ├── verification/               # Hard execution verification subsystem
│   │   └── manager.py              # VerificationManager (Expected vs Observed)
│   ├── recovery/                   # Failure classification and recovery
│   │   └── engine.py               # RecoveryEngine (4-tier escalation ladder)
│   ├── memory/                     # Episodic and semantic experience store
│   │   └── provider.py             # ChromaProvider (ChromaDB + SQLite)
│   ├── api/                        # FastAPI route controllers
│   ├── config.py                   # Pydantic runtime configuration
│   └── main.py                     # Backend application entry point
├── observatory/                    # Pilot Agent Observatory (:3001 / :8766)
│   ├── backend/                    # Telemetry FastAPI event server (:8766)
│   └── frontend/                   # React + Vite + Tailwind dashboard (:3001)
├── frontend/                       # Primary user application (:1420)
├── tests/                          # Comprehensive pytest test suite (109 tests)
├── docs/                           # Modular documentation specs
└── run_all.py                      # Multi-process development orchestrator
```

---

## Adding a Custom LangGraph Node

To insert a new operational step (e.g., `audit_security_node`) into the agent lifecycle:

### Step 1: Define New State Fields (if needed)
Modify `backend/agent/state.py`:
```python
class AgentState(TypedDict):
    # Existing fields...
    security_audit_passed: bool
```

### Step 2: Implement the Node Function
Add the node logic in `backend/agent/nodes.py`:
```python
async def audit_security_node(state: AgentState) -> dict:
    """Validate target URL and planned action against organizational security policy."""
    target_url = state.get("current_url")
    # Custom inspection logic...
    is_safe = not any(banned in (target_url or "") for banned in ["malicious-domain.com"])
    
    return {
        "security_audit_passed": is_safe,
        "status": "running" if is_safe else "blocked",
        "blocked_reason": None if is_safe else "Target URL flagged by security policy"
    }
```

### Step 3: Register the Node in the StateGraph
Update `backend/agent/graph.py`:
```python
def build_graph():
    graph = StateGraph(AgentState)
    
    # 1. Register node
    graph.add_node("audit_security", nodes.audit_security_node)
    
    # 2. Add edges
    graph.add_edge("auth_check", "audit_security")
    
    def security_router(state: AgentState) -> str:
        if not state.get("security_audit_passed"):
            return "complete"
        return "navigate"
        
    graph.add_conditional_edges("audit_security", security_router)
    # ...
```

---

## Adding a New Local Model Profile

To add support for a newly released local Ollama model (e.g., `llama3.2:3b`):

Edit `backend/llm/registry.py`:
```python
DEFAULT_KNOWN_MODELS.append(
    ModelMetadata(
        model_name="llama3.2:3b",
        capabilities=[
            ModelCapability.REASONING,
            ModelCapability.GENERAL,
            ModelCapability.LIGHTWEIGHT,
            ModelCapability.FAST,
            ModelCapability.TOOL_CALLING,
        ],
        priority=8,
        context_window=8192,
        latency_tier="low",
    )
)
```

---

## Creating Domain Plugins

Agentic Pilot features a plugin framework (`backend/plugins/`) for intercepting tasks targeting specific platforms (e.g., GitHub, Jira, Salesforce):

```python
from backend.plugins import BasePlugin

class GitHubPlugin(BasePlugin):
    plugin_id = "github_automation"
    domain_match = ["github.com"]

    async def preprocess_dom(self, dom_manifest):
        """Add domain-specific element priorities."""
        return dom_manifest

    async def custom_verification(self, action, result):
        """Custom PR creation or commit verification."""
        return True
```

---

*Related Pages:*
* [[Agent Execution Lifecycle|Agent-Execution-Lifecycle]]
* [[Testing & Evaluation|Testing-and-Evaluation]]
* [[Architecture|Architecture]]
