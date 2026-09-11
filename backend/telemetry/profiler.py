"""System-wide performance profiling and latency measurement for Agentic Pilot.

Measures and records baseline and post-optimization timings for:
- Application startup
- API request roundtrips
- Intent parsing
- Task decomposition & capability analysis
- Model routing and model switching
- RAG retrieval and embedding generation
- Episodic & procedural memory retrieval
- LLM inference
- Playwright startup, navigation, and DOM extraction
- Screenshot capture and Vision-Language inference
- State verification and strategy recovery
- Database read/write operations
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import time
from typing import Any, AsyncIterator
from pydantic import BaseModel, Field

from backend.config import get_config
from backend.db.database import resolve_path

logger = logging.getLogger("pilot.telemetry.profiler")


class ProfileRecord(BaseModel):
    """Structured record of a single measured system operation."""

    operation: str
    start_time: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    end_time: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    duration_ms: float = 0.0
    model: str = "none"
    cache_hit: bool = False
    task_id: str = "global"
    subtask_id: str = "root"
    metadata: dict[str, Any] = Field(default_factory=dict)


class LatencyProfiler:
    """Collects fine-grained operation timings and computes latency distributions."""

    def __init__(self, log_dir: Path | None = None) -> None:
        self.log_dir = log_dir or (resolve_path(get_config().log_dir) / "profiling")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.profile_file = self.log_dir / "profile_events.jsonl"
        self._in_memory_records: list[ProfileRecord] = []

    def record(
        self,
        operation: str,
        duration_ms: float,
        model: str = "none",
        cache_hit: bool = False,
        task_id: str = "global",
        subtask_id: str = "root",
        metadata: dict[str, Any] | None = None,
        start_time: str | None = None,
    ) -> ProfileRecord:
        """Record an operation measurement."""
        now = datetime.now(UTC).isoformat()
        rec = ProfileRecord(
            operation=operation,
            start_time=start_time or now,
            end_time=now,
            duration_ms=round(duration_ms, 2),
            model=model,
            cache_hit=cache_hit,
            task_id=task_id,
            subtask_id=subtask_id,
            metadata=metadata or {},
        )
        self._in_memory_records.append(rec)
        try:
            with open(self.profile_file, "a", encoding="utf-8") as f:
                f.write(rec.model_dump_json() + "\n")
        except Exception as exc:
            logger.debug("Failed to write profile record: %s", exc)
        return rec

    @asynccontextmanager
    async def measure(
        self,
        operation: str,
        model: str = "none",
        cache_hit: bool = False,
        task_id: str = "global",
        subtask_id: str = "root",
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Async context manager to time an operation and log results."""
        start_iso = datetime.now(UTC).isoformat()
        t0 = time.perf_counter()
        ctx_meta: dict[str, Any] = metadata.copy() if metadata else {}
        try:
            yield ctx_meta
        finally:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            actual_hit = ctx_meta.pop("cache_hit", cache_hit)
            actual_model = ctx_meta.pop("model", model)
            self.record(
                operation=operation,
                duration_ms=elapsed_ms,
                model=actual_model,
                cache_hit=actual_hit,
                task_id=task_id,
                subtask_id=subtask_id,
                metadata=ctx_meta,
                start_time=start_iso,
            )

    def get_summary_by_operation(self) -> dict[str, dict[str, Any]]:
        """Compute latency percentiles (mean, min, p50, p95, max) for every operation."""
        durations: dict[str, list[float]] = {}
        for r in self._in_memory_records:
            durations.setdefault(r.operation, []).append(r.duration_ms)

        # Also load from file if in-memory list is empty
        if not durations and self.profile_file.exists():
            try:
                with open(self.profile_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        data = json.loads(line)
                        op = data.get("operation", "unknown")
                        durations.setdefault(op, []).append(data.get("duration_ms", 0.0))
            except Exception:
                pass

        summary: dict[str, dict[str, Any]] = {}
        for op, vals in durations.items():
            if not vals:
                continue
            sorted_vals = sorted(vals)
            n = len(sorted_vals)
            p50_idx = int(0.50 * n)
            p95_idx = min(int(0.95 * n), n - 1)
            summary[op] = {
                "count": n,
                "mean_ms": round(sum(sorted_vals) / n, 2),
                "min_ms": round(sorted_vals[0], 2),
                "p50_ms": round(sorted_vals[p50_idx], 2),
                "p95_ms": round(sorted_vals[p95_idx], 2),
                "max_ms": round(sorted_vals[-1], 2),
            }
        return summary


# Global singleton profiler
profiler = LatencyProfiler()


async def run_baseline_profile_audit() -> dict[str, Any]:
    """Execute a comprehensive baseline latency audit across the 16 core operations."""
    logger.info("Starting baseline latency profiling audit...")
    audit_results: dict[str, Any] = {}

    # 1. Application Startup Simulation
    t0 = time.perf_counter()
    from backend.db.database import database
    await database.connect()
    startup_duration = (time.perf_counter() - t0) * 1000
    profiler.record("app_startup", startup_duration, metadata={"phase": "db_connect"})
    audit_results["app_startup_ms"] = round(startup_duration, 2)

    # 2. Database Read/Write Latency
    t0 = time.perf_counter()
    test_task_id = f"audit_{int(time.time())}"
    await database.create_task(test_task_id, "Audit task", None)
    await database.add_event(test_task_id, "AUDIT_EVENT", "Profiling DB write")
    task_row = await database.get_task(test_task_id)
    db_duration = (time.perf_counter() - t0) * 1000
    profiler.record("database_roundtrip", db_duration, task_id=test_task_id)
    audit_results["database_roundtrip_ms"] = round(db_duration, 2)

    # 3. Model Registry & Probe Latency
    t0 = time.perf_counter()
    from backend.llm.registry import model_registry
    models = model_registry.list_registered_models()
    reg_duration = (time.perf_counter() - t0) * 1000
    profiler.record("model_registry_list", reg_duration, metadata={"count": len(models)})
    audit_results["model_registry_ms"] = round(reg_duration, 2)

    # 4. Model Routing Latency
    t0 = time.perf_counter()
    from backend.llm.router import model_router
    decision = model_router.route(task_type="coding", input_text="write python function")
    route_duration = (time.perf_counter() - t0) * 1000
    profiler.record("model_routing", route_duration, model=decision.selected_model)
    audit_results["model_routing_ms"] = round(route_duration, 2)

    # 5. RAG Knowledge Retrieval Latency (Cold vs Warm)
    from backend.rag.retriever import knowledge_retriever
    t0 = time.perf_counter()
    cold_res = await knowledge_retriever.retrieve("authentication policy")
    rag_cold_ms = (time.perf_counter() - t0) * 1000
    profiler.record("rag_retrieval_cold", rag_cold_ms, cache_hit=cold_res.cache_hit)
    audit_results["rag_retrieval_cold_ms"] = round(rag_cold_ms, 2)

    t0 = time.perf_counter()
    warm_res = await knowledge_retriever.retrieve("authentication policy")
    rag_warm_ms = (time.perf_counter() - t0) * 1000
    profiler.record("rag_retrieval_warm", rag_warm_ms, cache_hit=warm_res.cache_hit)
    audit_results["rag_retrieval_warm_ms"] = round(rag_warm_ms, 2)

    # 6. Episodic Memory Lookup Latency
    from backend.memory.provider import memory_manager
    t0 = time.perf_counter()
    memories = await memory_manager.retrieve_relevant("test query", limit=2)
    mem_duration = (time.perf_counter() - t0) * 1000
    profiler.record("memory_retrieval", mem_duration, metadata={"count": len(memories)})
    audit_results["memory_retrieval_ms"] = round(mem_duration, 2)

    # 7. Verification Latency
    from backend.verification.manager import verification_manager
    t0 = time.perf_counter()
    v_res = await verification_manager.verify_task_completion(
        page=None,
        intent_action="navigate",
        intent_site="google.com",
        current_url="https://google.com",
        navigation_succeeded=True,
    )
    verif_duration = (time.perf_counter() - t0) * 1000
    profiler.record("verification_check", verif_duration, metadata={"verified": v_res.verified})
    audit_results["verification_check_ms"] = round(verif_duration, 2)

    # 8. Recovery Classification Latency
    from backend.recovery.engine import recovery_engine
    t0 = time.perf_counter()
    failure_type = recovery_engine.classify_failure("Navigation timeout net::ERR_CONNECTION_TIMED_OUT")
    strategy = recovery_engine.select_strategy(failure_type, retry_count=0)
    recov_duration = (time.perf_counter() - t0) * 1000
    profiler.record("recovery_diagnosis", recov_duration, metadata={"type": failure_type, "strategy": strategy})
    audit_results["recovery_diagnosis_ms"] = round(recov_duration, 2)

    # Clean up test task
    await database.update_task(test_task_id, status="completed")

    logger.info("Baseline profiling audit completed: %s", audit_results)
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "baseline_metrics": audit_results,
        "operation_summary": profiler.get_summary_by_operation(),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = asyncio.run(run_baseline_profile_audit())
    print("\n--- BASELINE LATENCY AUDIT REPORT ---")
    print(json.dumps(results, indent=2))
