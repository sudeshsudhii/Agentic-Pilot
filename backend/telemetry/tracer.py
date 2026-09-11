"""Observability, telemetry, and experiment metrics for Agentic Pilot (Phase 10 / R14).

Provides append-only tracing of all agent decisions, LLM calls, tool interactions,
verification checks, and recovery events. Computes research metrics across tasks.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.config import get_config
from backend.db.database import resolve_path


class TelemetryTracer:
    """Logs detailed execution traces and calculates research experiment metrics."""

    def __init__(self) -> None:
        """Initialize the tracer and ensure log directory exists."""
        self.log_dir = resolve_path(get_config().log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.trace_file = self.log_dir / "traces.jsonl"

    def record_trace(self, task_id: str, component: str, event: str, metadata: dict[str, Any] | None = None) -> None:
        """Append a trace record to the JSONL log file."""
        trace = {
            "timestamp": datetime.now(UTC).isoformat(),
            "task_id": task_id,
            "component": component,
            "event": event,
            "metadata": metadata or {},
        }
        
        try:
            with open(self.trace_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(trace) + "\n")
        except Exception:
            pass

    def record_llm_call(self, task_id: str, prompt: str, response: str, latency_ms: int, model: str) -> None:
        """Record an LLM generation event."""
        self.record_trace(task_id, "llm", "completion", {
            "model": model,
            "prompt_length": len(prompt),
            "response_length": len(response),
            "latency_ms": latency_ms,
            "prompt": prompt[:500],  # truncated for safety
            "response": response[:500],
        })

    def record_browser_action(self, task_id: str, action_type: str, success: bool, duration_ms: int, error: str | None = None) -> None:
        """Record a browser action execution."""
        self.record_trace(task_id, "browser", action_type, {
            "success": success,
            "duration_ms": duration_ms,
            "error": error,
        })

    def record_recovery_attempt(self, task_id: str, failure_type: str, strategy: str, outcome: str) -> None:
        """Record a recovery attempt and strategy outcome (R10/R14)."""
        self.record_trace(task_id, "recovery", "attempt", {
            "failure_type": failure_type,
            "strategy": strategy,
            "outcome": outcome,
        })

    def record_verification_result(self, task_id: str, verification_type: str, verified: bool, confidence: float, message: str = "") -> None:
        """Record a verification check (R09/R14)."""
        self.record_trace(task_id, "verification", "check", {
            "type": verification_type,
            "verified": verified,
            "confidence": confidence,
            "message": message,
        })

    def record_rag_retrieval(
        self,
        task_id: str,
        query: str,
        retrieved_count: int,
        latency_ms: float,
        cache_hit: bool,
        sources: list[str] | None = None,
        scores: list[float] | None = None,
    ) -> None:
        """Record a RAG knowledge retrieval event (R13)."""
        self.record_trace(task_id, "rag", "retrieval", {
            "query": query[:200],
            "total_found": retrieved_count,
            "latency_ms": latency_ms,
            "cache_hit": cache_hit,
            "sources": sources or [],
            "scores": scores or [],
        })

    def record_model_routing(
        self,
        task_id: str,
        selected_model: str,
        role: str,
        reason: str,
        model_switch: bool,
        latency_tier: str = "medium",
        fallback_used: bool = False,
    ) -> None:
        """Record a model routing decision (Multi-Model Architecture)."""
        self.record_trace(task_id, "model_routing", "selection", {
            "selected_model": selected_model,
            "role": role,
            "reason": reason,
            "model_switch": model_switch,
            "latency_tier": latency_tier,
            "fallback_used": fallback_used,
        })

    def record_task_summary(self, task_id: str, status: str, duration_ms: int, step_count: int, error: str | None = None) -> None:
        """Record final task completion metrics for experiments."""
        self.record_trace(task_id, "agent", "task_summary", {
            "status": status,
            "duration_ms": duration_ms,
            "step_count": step_count,
            "error": error,
        })

    def get_aggregated_metrics(self, task_ids: list[str] | None = None) -> dict[str, Any]:
        """Parse traces.jsonl and compute research metrics (R14).

        Calculates:
        - Task completion rate (%)
        - Recovery success rate (%)
        - Verification pass rate (%)
        - Mean execution duration (s)
        - Mean steps per task
        - Total LLM calls and average latency (ms)
        - RAG retrieval metrics (queries, cache hit rate, latency, retrieved chunks)
        - Multi-model routing metrics (total routings, switch count, fallback rate, usage by role)
        """
        if not self.trace_file.exists():
            return {
                "total_tasks": 0,
                "completed_tasks": 0,
                "completion_rate": 0.0,
                "total_recoveries": 0,
                "recovery_success_rate": 0.0,
                "total_verifications": 0,
                "verification_pass_rate": 0.0,
                "mean_duration_ms": 0.0,
                "mean_steps": 0.0,
                "total_llm_calls": 0,
                "mean_llm_latency_ms": 0.0,
                "total_rag_queries": 0,
                "rag_cache_hits": 0,
                "rag_cache_hit_rate": 0.0,
                "mean_rag_retrieval_latency_ms": 0.0,
                "mean_rag_retrieved_chunks": 0.0,
                "total_model_routings": 0,
                "model_switch_count": 0,
                "model_fallback_rate": 0.0,
                "model_usage_by_role": {},
                "model_usage_by_model": {},
            }

        task_summaries: list[dict[str, Any]] = []
        recovery_events: list[dict[str, Any]] = []
        verification_events: list[dict[str, Any]] = []
        rag_events: list[dict[str, Any]] = []
        routing_events: list[dict[str, Any]] = []
        llm_latencies: list[int] = []

        try:
            with open(self.trace_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    t_id = record.get("task_id")
                    if task_ids and t_id not in task_ids:
                        continue

                    component = record.get("component")
                    event = record.get("event")
                    meta = record.get("metadata", {})

                    if component == "agent" and event == "task_summary":
                        task_summaries.append(meta)
                    elif component == "recovery" and event == "attempt":
                        recovery_events.append(meta)
                    elif component == "verification" and event == "check":
                        verification_events.append(meta)
                    elif component == "rag" and event == "retrieval":
                        rag_events.append(meta)
                    elif component == "model_routing" and event == "selection":
                        routing_events.append(meta)
                    elif component == "llm" and event == "completion":
                        if "latency_ms" in meta:
                            llm_latencies.append(meta["latency_ms"])
        except Exception:
            pass

        total_tasks = len(task_summaries)
        completed_tasks = sum(1 for s in task_summaries if s.get("status") == "completed")
        completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0.0

        successful_recoveries = sum(1 for r in recovery_events if r.get("outcome") == "success")
        recovery_rate = (successful_recoveries / len(recovery_events) * 100) if recovery_events else 0.0

        passed_verifications = sum(1 for v in verification_events if v.get("verified") is True)
        verification_rate = (passed_verifications / len(verification_events) * 100) if verification_events else 0.0

        durations = [s.get("duration_ms", 0) for s in task_summaries if "duration_ms" in s]
        mean_dur = sum(durations) / len(durations) if durations else 0.0

        steps = [s.get("step_count", 0) for s in task_summaries if "step_count" in s]
        mean_steps = sum(steps) / len(steps) if steps else 0.0

        mean_llm_lat = sum(llm_latencies) / len(llm_latencies) if llm_latencies else 0.0

        # RAG aggregations
        total_rag_queries = len(rag_events)
        rag_cache_hits = sum(1 for r in rag_events if r.get("cache_hit") is True)
        rag_cache_hit_rate = round(rag_cache_hits / total_rag_queries * 100, 2) if total_rag_queries > 0 else 0.0
        rag_latencies = [r.get("latency_ms", 0.0) for r in rag_events if "latency_ms" in r]
        mean_rag_lat = round(sum(rag_latencies) / len(rag_latencies), 1) if rag_latencies else 0.0
        rag_chunks = [r.get("total_found", 0) for r in rag_events if "total_found" in r]
        mean_rag_chunks = round(sum(rag_chunks) / len(rag_chunks), 2) if rag_chunks else 0.0

        # Multi-model aggregations
        total_model_routings = len(routing_events)
        model_switch_count = sum(1 for r in routing_events if r.get("model_switch") is True)
        fallbacks_used = sum(1 for r in routing_events if r.get("fallback_used") is True)
        model_fallback_rate = round(fallbacks_used / total_model_routings * 100, 2) if total_model_routings > 0 else 0.0
        model_switches_per_task = round(model_switch_count / total_tasks, 2) if total_tasks > 0 else 0.0

        # Routing Overhead & Efficiency metrics (Section 37)
        # Routing Overhead = routing decision latency (~1.5ms) + model switching loading penalty (~250ms per switch)
        routing_overhead_ms = round((total_model_routings * 1.5) + (model_switch_count * 250.0), 1)
        overhead_factor = max(1.0, 1.0 + (model_switches_per_task * 0.05))
        routing_efficiency = round(completion_rate / overhead_factor, 2)

        model_usage_by_role: dict[str, int] = {}
        model_usage_by_model: dict[str, int] = {}
        for r in routing_events:
            role = r.get("role", "general")
            model = r.get("selected_model", "unknown")
            model_usage_by_role[role] = model_usage_by_role.get(role, 0) + 1
            model_usage_by_model[model] = model_usage_by_model.get(model, 0) + 1

        return {
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "completion_rate": round(completion_rate, 2),
            "total_recoveries": len(recovery_events),
            "recovery_success_rate": round(recovery_rate, 2),
            "total_verifications": len(verification_events),
            "verification_pass_rate": round(verification_rate, 2),
            "mean_duration_ms": round(mean_dur, 1),
            "mean_steps": round(mean_steps, 2),
            "total_llm_calls": len(llm_latencies),
            "mean_llm_latency_ms": round(mean_llm_lat, 1),
            "total_rag_queries": total_rag_queries,
            "rag_cache_hits": rag_cache_hits,
            "rag_cache_hit_rate": rag_cache_hit_rate,
            "mean_rag_retrieval_latency_ms": mean_rag_lat,
            "mean_rag_retrieved_chunks": mean_rag_chunks,
            "total_model_routings": total_model_routings,
            "model_switch_count": model_switch_count,
            "model_switches_per_task": model_switches_per_task,
            "model_fallback_rate": model_fallback_rate,
            "routing_overhead_ms": routing_overhead_ms,
            "routing_efficiency": routing_efficiency,
            "model_usage_by_role": model_usage_by_role,
            "model_usage_by_model": model_usage_by_model,
        }



tracer = TelemetryTracer()
