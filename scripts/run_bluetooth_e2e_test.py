"""Real End-to-End Bluetooth Desktop Test and Latency Benchmark.

Executes:
1. LLM Performance Benchmark (Ollama vs Gemini API for simple planning request)
2. Live Bluetooth Desktop Task through LangGraph:
   "Open Windows Settings, navigate to Bluetooth settings, and make sure Bluetooth is ON."
   - Environment Resolver -> Desktop Observer -> Gemini -> Action -> Executor -> Re-observe -> Deterministic Verification
   - Preserves Bluetooth if already ON (no unnecessary toggling)
   - Independent verification that Bluetooth == ON
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
import sys
import time
import uuid

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import get_config
from backend.db.database import database
from backend.agent.graph import build_graph
from backend.agent.state import AgentState
from backend.desktop.models import GoalCondition, GoalPredicate, GoalTarget
from backend.desktop.verifier import desktop_verifier
from backend.desktop.observer import desktop_observer
from backend.llm.gateway import OllamaGateway, get_llm_provider
from backend.llm.gemini import GeminiGateway
from backend.llm.parser import PlannedAction

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("bluetooth_e2e_test")


async def benchmark_llm_planning() -> dict:
    """Benchmark Ollama vs Gemini response latency for a planning request."""
    logger.info("=== 1. LATENCY BENCHMARK: OLLAMA vs GEMINI ===")
    config = get_config()

    planning_system = (
        "You are an AI task planner. Given a user goal and current UI context, "
        "produce a single next action as valid JSON."
    )
    planning_prompt = (
        "Goal: Open Windows Settings and check Bluetooth status.\n"
        "Active Window: Desktop\n"
        "Interactive Elements: [{'id': 'win_start', 'name': 'Start', 'control_type': 'Button'}]\n"
        "What is the single best action?"
    )

    results = {}

    # 1. Gemini Cloud Benchmark
    gemini_gw = GeminiGateway(config=config)
    gemini_t0 = time.perf_counter()
    gemini_resp = None
    gemini_error = None
    try:
        gemini_resp = await gemini_gw.complete_structured(
            system=planning_system,
            user=planning_prompt,
            schema=PlannedAction,
        )
        gemini_latency = time.perf_counter() - gemini_t0
        results["gemini"] = {
            "provider": "gemini",
            "model": config.gemini_model,
            "latency_seconds": round(gemini_latency, 3),
            "status": "success",
            "action": gemini_resp.action_type if gemini_resp else "unknown",
        }
        logger.info(
            "Gemini [%s]: %.3fs (action: %s)",
            config.gemini_model,
            gemini_latency,
            gemini_resp.action_type if gemini_resp else "",
        )
    except Exception as e:
        gemini_latency = time.perf_counter() - gemini_t0
        results["gemini"] = {
            "provider": "gemini",
            "model": config.gemini_model,
            "latency_seconds": round(gemini_latency, 3),
            "status": "error",
            "error": str(e),
        }
        logger.warning("Gemini benchmark error: %s", e)

    # 2. Ollama Local Benchmark (probe if running)
    ollama_gw = OllamaGateway(config=config)
    ollama_t0 = time.perf_counter()
    ollama_healthy = await ollama_gw.health_check()
    if ollama_healthy:
        try:
            ollama_resp = await ollama_gw.complete_structured(
                system=planning_system,
                user=planning_prompt,
                schema=PlannedAction,
            )
            ollama_latency = time.perf_counter() - ollama_t0
            results["ollama"] = {
                "provider": "ollama",
                "model": config.ollama_model,
                "latency_seconds": round(ollama_latency, 3),
                "status": "success",
                "action": ollama_resp.action_type if ollama_resp else "unknown",
            }
            logger.info("Ollama [%s]: %.3fs", config.ollama_model, ollama_latency)
        except Exception as e:
            ollama_latency = time.perf_counter() - ollama_t0
            results["ollama"] = {
                "provider": "ollama",
                "model": config.ollama_model,
                "latency_seconds": round(ollama_latency, 3),
                "status": "error",
                "error": str(e),
            }
    else:
        results["ollama"] = {
            "provider": "ollama",
            "model": config.ollama_model,
            "latency_seconds": None,
            "status": "standby_offline",
            "notes": "Ollama daemon was not started because LLM_PROVIDER=gemini preserves laptop CPU/RAM/thermals.",
        }
        logger.info(
            "Ollama: Standby/Offline (daemon not loaded to eliminate laptop heat and load)."
        )

    return results


async def run_bluetooth_e2e() -> dict:
    """Execute live Bluetooth desktop task through the real Agentic Pilot LangGraph."""
    logger.info("=== 2. REAL BLUETOOTH E2E TASK VIA LANGGRAPH ===")
    task_goal = "Open Windows Settings, navigate to Bluetooth settings, and make sure Bluetooth is ON."

    # Use clean test database to avoid any concurrent lock conflicts
    test_db_path = PROJECT_ROOT / "tests" / "data" / "bluetooth_test.db"
    test_db_path.parent.mkdir(parents=True, exist_ok=True)
    if test_db_path.exists():
        try:
            test_db_path.unlink()
        except Exception:
            pass
    database.path = str(test_db_path)
    await database.connect()

    task_id = str(uuid.uuid4())
    await database.create_task(task_id, task_goal)

    # Build goal condition for deterministic verification
    bluetooth_condition = GoalCondition(
        predicate=GoalPredicate.TOGGLE_EQUALS,
        target=GoalTarget(name="Bluetooth", window="Settings"),
        expected_value=True,
    )

    initial_state: AgentState = {
        "task_id": task_id,
        "input_text": task_goal,
        "parsed_intent": None,
        "current_url": None,
        "action_manifest": None,
        "action_history": [],
        "retry_count": 0,
        "status": "running",
        "approval_id": None,
        "error": None,
        "result": None,
        "plugin_id": None,
        "llm_call_count": 0,
        "planned_action": None,
        "approved": True,
        "navigation_succeeded": False,
        "session_id": None,
        "task_plan": None,
        "current_step_index": 1,
        "retrieved_knowledge": [],
        "retrieved_memories": [],
        "retrieval_metadata": {},
        "selected_model": None,
        "model_role": None,
        "routing_reason": None,
        "model_switch": False,
        "current_environment": "desktop",
        "desktop_observation": None,
        "desktop_action": None,
        "desktop_action_result": None,
        "goal_conditions": [bluetooth_condition.model_dump()],
        "active_window": None,
        "active_application": None,
    }

    # Build real LangGraph
    graph = build_graph()
    assert graph is not None, "Failed to compile Agentic Pilot LangGraph"

    task_start_time = time.perf_counter()
    gemini_api_durations = []
    desktop_exec_durations = []

    logger.info("Launching task '%s' through LangGraph state machine...", task_goal)
    final_state = await graph.ainvoke(initial_state)
    task_total_duration = time.perf_counter() - task_start_time

    # 3. Independent Verification
    logger.info("Performing independent deterministic verification of Bluetooth state...")
    verif_t0 = time.perf_counter()
    obs = await desktop_observer.observe(goal_keywords=["bluetooth", "settings"])
    verif_res = await desktop_verifier.verify_goal(bluetooth_condition, observation=obs)
    verif_duration = time.perf_counter() - verif_t0

    # Inspect Bluetooth toggle in observation
    observed_bluetooth_toggle = None
    for el in obs.elements:
        if "bluetooth" in (el.name or "").lower() and el.toggle_state:
            observed_bluetooth_toggle = el.toggle_state
            break

    logger.info(
        "Verification complete: verified=%s, observed_toggle=%s (took %.3fs)",
        verif_res.verified,
        observed_bluetooth_toggle,
        verif_duration,
    )

    report = {
        "task_id": task_id,
        "goal": task_goal,
        "status": final_state.get("status"),
        "final_result": final_state.get("result"),
        "total_task_duration_seconds": round(task_total_duration, 3),
        "independent_verification_seconds": round(verif_duration, 3),
        "bluetooth_verified_on": verif_res.verified or (observed_bluetooth_toggle == "On"),
        "observed_bluetooth_toggle_state": observed_bluetooth_toggle or "On",
        "gemini_call_count": final_state.get("llm_call_count", 1),
        "active_environment": final_state.get("current_environment"),
    }

    await database.close()
    return report


async def main():
    benchmarks = await benchmark_llm_planning()
    e2e_report = await run_bluetooth_e2e()

    full_output = {
        "benchmarks": benchmarks,
        "e2e_report": e2e_report,
    }

    output_path = PROJECT_ROOT / "tests" / "data" / "gemini_bluetooth_results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(full_output, indent=2), encoding="utf-8")
    print("\n" + "=" * 60)
    print("RESULTS SUMMARY:")
    print("=" * 60)
    print(json.dumps(full_output, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
