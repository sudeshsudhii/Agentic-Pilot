"""Experiment runner for automated ablation studies and evaluation (Phase 10 / R14)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.config import PilotConfig, get_config
from backend.db.database import database, resolve_path
from backend.experiment.config import ABLATION_PRESETS, ExperimentConfig, STANDARD_BENCHMARK_TASKS
from backend.telemetry.tracer import tracer

logger = logging.getLogger("pilot.experiment.runner")


class ExperimentRunner:
    """Orchestrates automated ablation benchmarks and comparative evaluations."""

    def __init__(self, output_dir: Path | None = None) -> None:
        self.output_dir = output_dir or resolve_path(get_config().experiment_output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)


    async def run_experiment(
        self,
        config: ExperimentConfig,
        tasks: list[str] | None = None,
    ) -> dict[str, Any]:
        """Execute a single experimental evaluation run.

        Args:
            config: The ExperimentConfig defining ablation overrides
            tasks: Optional custom task list, defaults to STANDARD_BENCHMARK_TASKS

        Returns:
            Structured dictionary containing task results and aggregate metrics.
        """
        run_id = f"exp_{config.name}_{int(time.time())}"
        benchmark_tasks = tasks or config.benchmark_tasks or STANDARD_BENCHMARK_TASKS
        logger.info("Starting experiment run_id=%s preset=%s tasks=%d", run_id, config.name, len(benchmark_tasks))

        # Backup base config
        base_cfg = get_config()
        original_flags = {
            "enable_evidence": base_cfg.enable_evidence,
            "enable_verification": base_cfg.enable_verification,
            "enable_recovery": base_cfg.enable_recovery,
            "enable_memory": base_cfg.enable_memory,
            "enable_rag": base_cfg.enable_rag,
            "enable_multi_model": base_cfg.enable_multi_model,
            "model_routing_strategy": base_cfg.model_routing_strategy,
            "rag_hybrid_search": base_cfg.rag_hybrid_search,
            "rag_reranking": base_cfg.rag_reranking,
        }

        # Apply experiment overrides
        for k, v in config.pilot_config_overrides.items():
            if hasattr(base_cfg, k):
                setattr(base_cfg, k, v)

        task_records: list[dict[str, Any]] = []
        started_at = datetime.now(UTC).isoformat()

        try:
            for i, task_text in enumerate(benchmark_tasks, 1):
                logger.info("Executing experiment task [%d/%d]: %s", i, len(benchmark_tasks), task_text[:60])
                task_id = str(uuid.uuid4())
                task_start = time.perf_counter()

                # Run task through Runner or direct graph
                task_status = "completed"
                error_msg = None
                step_count = 1

                try:
                    from backend.agent.graph import create_agent_graph
                    graph = create_agent_graph()
                    state: dict[str, Any] = {
                        "task_id": task_id,
                        "input_text": task_text,
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
                        "approved": True,  # Auto-approve in benchmark mode
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
                    }


                    # Execute graph
                    final_state = await graph.ainvoke(state)
                    task_status = final_state.get("status", "failed")
                    error_msg = final_state.get("error")
                    step_count = final_state.get("llm_call_count", 1)

                except Exception as exc:
                    task_status = "failed"
                    error_msg = str(exc)
                    logger.warning("Experiment task error task_id=%s: %s", task_id, exc)

                duration_ms = int((time.perf_counter() - task_start) * 1000)

                task_records.append({
                    "task_id": task_id,
                    "task_text": task_text,
                    "status": task_status,
                    "duration_ms": duration_ms,
                    "step_count": step_count,
                    "error": error_msg,
                })

        finally:
            # Restore original configuration
            for k, v in original_flags.items():
                setattr(base_cfg, k, v)

        # Compute aggregate metrics
        total = len(task_records)
        completed = sum(1 for r in task_records if r["status"] == "completed")
        success_rate = (completed / total * 100) if total > 0 else 0.0
        avg_duration = sum(r["duration_ms"] for r in task_records) / total if total > 0 else 0.0
        avg_steps = sum(r["step_count"] for r in task_records) / total if total > 0 else 0.0

        results: dict[str, Any] = {
            "run_id": run_id,
            "preset": config.name,
            "description": config.description,
            "started_at": started_at,
            "completed_at": datetime.now(UTC).isoformat(),
            "config_overrides": config.pilot_config_overrides,
            "metrics": {
                "total_tasks": total,
                "completed_tasks": completed,
                "success_rate_percent": round(success_rate, 2),
                "average_duration_ms": round(avg_duration, 1),
                "average_steps": round(avg_steps, 2),
            },
            "task_records": task_records,
        }

        # Save to disk
        out_file = self.output_dir / f"{run_id}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)

        logger.info("Experiment %s complete: Success Rate=%.1f%% Saved to %s", run_id, success_rate, out_file)
        return results

    async def run_ablation_comparison(
        self,
        preset_names: list[str] | None = None,
        tasks: list[str] | None = None,
    ) -> dict[str, Any]:
        """Run multiple ablation presets and compare results side-by-side."""
        presets_to_run = preset_names or list(ABLATION_PRESETS.keys())
        comparison: dict[str, Any] = {
            "comparison_id": f"ablation_study_{int(time.time())}",
            "timestamp": datetime.now(UTC).isoformat(),
            "presets_evaluated": presets_to_run,
            "results_by_preset": {},
        }

        for preset_name in presets_to_run:
            if preset_name not in ABLATION_PRESETS:
                continue
            cfg = ABLATION_PRESETS[preset_name]
            res = await self.run_experiment(cfg, tasks=tasks)
            comparison["results_by_preset"][preset_name] = res["metrics"]

        # Save comparative study report
        comp_file = self.output_dir / f"{comparison['comparison_id']}.json"
        with open(comp_file, "w", encoding="utf-8") as f:
            json.dump(comparison, f, indent=2)

        return comparison


experiment_runner = ExperimentRunner()
