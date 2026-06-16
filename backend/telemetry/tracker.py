"""Telemetry tracker for Agentic Pilot."""

from __future__ import annotations
import json
import time
from pathlib import Path

class TelemetryTracker:
    """Tracks latency and success metrics across the entire task lifecycle."""

    def __init__(self):
        self.active_tasks = {}

    def start_task(self, task_id: str):
        self.active_tasks[task_id] = {
            "task_start_time": time.perf_counter(),
            "browser_launch_ms": 0,
            "llm_latency_ms": 0,
            "memory_latency_ms": 0,
            "vision_latency_ms": 0,
            "verification_latency_ms": 0,
            "llm_call_count": 0,
            "retry_count": 0,
            "success": False,
        }
        
    def record_llm_call(self, task_id: str, latency_ms: int):
        if task_id in self.active_tasks:
            self.active_tasks[task_id]["llm_latency_ms"] += latency_ms
            self.active_tasks[task_id]["llm_call_count"] += 1
            
    def record_browser_launch(self, task_id: str, latency_ms: int):
        if task_id in self.active_tasks:
            self.active_tasks[task_id]["browser_launch_ms"] += latency_ms
            
    def record_retry(self, task_id: str):
        if task_id in self.active_tasks:
            self.active_tasks[task_id]["retry_count"] += 1
            
    def finish_task(self, task_id: str, success: bool):
        if task_id not in self.active_tasks:
            return
            
        record = self.active_tasks[task_id]
        record["task_duration_ms"] = int((time.perf_counter() - record["task_start_time"]) * 1000)
        record["success"] = success
        
        # Save telemetry trace
        output_dir = Path.home() / ".pilot" / "evidence" / task_id
        output_dir.mkdir(parents=True, exist_ok=True)
        
        with open(output_dir / "telemetry.json", "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)
            
        del self.active_tasks[task_id]

telemetry_tracker = TelemetryTracker()
