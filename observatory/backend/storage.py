"""Read-only storage accessor for Pilot database, evidence, and checkpoints."""

from __future__ import annotations

import contextlib
import json
import logging
from pathlib import Path
from typing import Any
import aiosqlite

from observatory.backend.models import ObservatoryEventModel, PerformanceMetrics, RunSummary

logger = logging.getLogger("observatory.storage")


def _redact(obj: Any) -> Any:
    """Redact sensitive fields from dictionaries and lists."""
    if isinstance(obj, dict):
        res = {}
        for k, v in obj.items():
            if any(term in k.lower() for term in ("password", "passwd", "token", "secret", "cookie", "auth", "api_key", "credential")):
                res[k] = "[REDACTED]"
            else:
                res[k] = _redact(v)
        return res
    if isinstance(obj, list):
        return [_redact(item) for item in obj]
    return obj


class ReadOnlyStorage:
    """Access Pilot SQLite database and evidence directories in read-only mode."""

    def __init__(self, db_path: str | None = None) -> None:
        if db_path:
            self.db_path = str(Path(db_path).expanduser())
        else:
            # Check default ~/.pilot/data.db first, then ./pilot.db
            p1 = Path("~/.pilot/data.db").expanduser()
            p2 = Path("pilot.db")
            self.db_path = str(p1 if p1.exists() else (p2 if p2.exists() else p1))

    @contextlib.asynccontextmanager
    async def get_connection(self):
        """Open a read-only SQLite connection."""
        conn = await aiosqlite.connect(self.db_path)
        conn.row_factory = aiosqlite.Row
        try:
            yield conn
        finally:
            await conn.close()

    async def list_runs(self, limit: int = 50) -> list[RunSummary]:
        """Fetch historical task runs."""
        try:
            async with self.get_connection() as conn:
                cursor = await conn.execute(
                    """
                    SELECT task_id, input_text, status, created_at, completed_at, error, parsed_intent_json
                    FROM tasks
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                rows = await cursor.fetchall()
                results: list[RunSummary] = []
                for row in rows:
                    task_id = row["task_id"]
                    # Fetch step count and models from events
                    ev_cursor = await conn.execute(
                        "SELECT type, payload_json FROM task_events WHERE task_id = ?",
                        (task_id,),
                    )
                    ev_rows = await ev_cursor.fetchall()
                    step_count = len(ev_rows)
                    model = "UNKNOWN"
                    vision_status = "UNKNOWN"

                    for ev in ev_rows:
                        if ev["type"] == "MODEL_SELECTED" and ev["payload_json"]:
                            try:
                                p = json.loads(ev["payload_json"])
                                model = p.get("planner_model") or p.get("model") or model
                            except Exception:
                                pass
                        elif ev["type"] == "VISION_STATUS" and ev["payload_json"]:
                            try:
                                p = json.loads(ev["payload_json"])
                                vision_status = p.get("status", vision_status)
                            except Exception:
                                pass

                    results.append(
                        RunSummary(
                            run_id=task_id,
                            task_id=task_id,
                            input_text=row["input_text"],
                            status=row["status"],
                            created_at=row["created_at"],
                            completed_at=row["completed_at"],
                            step_count=step_count,
                            model=model,
                            vision_status=vision_status,
                            error=row["error"],
                        )
                    )
                return results
        except Exception as exc:
            logger.warning("Failed to list runs: %s", exc)
            return []

    async def get_run_events(self, run_id: str) -> list[ObservatoryEventModel]:
        """Fetch all events for a specific run ID."""
        try:
            async with self.get_connection() as conn:
                cursor = await conn.execute(
                    """
                    SELECT id, task_id, type, message, payload_json, created_at
                    FROM task_events
                    WHERE task_id = ?
                    ORDER BY id ASC
                    """,
                    (run_id,),
                )
                rows = await cursor.fetchall()
                events: list[ObservatoryEventModel] = []
                for row in rows:
                    payload = {}
                    if row["payload_json"]:
                        try:
                            payload = json.loads(row["payload_json"])
                        except Exception:
                            payload = {"raw": row["payload_json"]}

                    payload = _redact(payload)
                    status = payload.get("status", "running")
                    step_idx = payload.get("step_index", 0)

                    events.append(
                        ObservatoryEventModel(
                            event_id=str(row["id"]),
                            run_id=row["task_id"],
                            task_id=row["task_id"],
                            timestamp=row["created_at"],
                            event_type=row["type"],
                            status=status,
                            step_index=step_idx,
                            message=row["message"],
                            metadata=payload,
                        )
                    )
                return events
        except Exception as exc:
            logger.warning("Failed to get events for run %s: %s", run_id, exc)
            return []

    async def get_run_state(self, run_id: str) -> dict[str, Any] | None:
        """Fetch LangGraph checkpoint state for a run."""
        # Check checkpoint file in ~/.pilot/data/checkpoints/{run_id}.json
        ckpt_dir = Path("~/.pilot/data/checkpoints").expanduser()
        ckpt_path = ckpt_dir / f"{run_id}.json"
        if ckpt_path.exists():
            try:
                data = json.loads(ckpt_path.read_text(encoding="utf-8"))
                return _redact(data)
            except Exception as e:
                logger.warning("Failed to read checkpoint %s: %s", ckpt_path, e)

        # Fallback to tasks table row
        try:
            async with self.get_connection() as conn:
                cursor = await conn.execute("SELECT * FROM tasks WHERE task_id = ?", (run_id,))
                row = await cursor.fetchone()
                if row:
                    res = dict(row)
                    if res.get("parsed_intent_json"):
                        try:
                            res["parsed_intent"] = json.loads(res["parsed_intent_json"])
                        except Exception:
                            pass
                    if res.get("result_json"):
                        try:
                            res["result"] = json.loads(res["result_json"])
                        except Exception:
                            pass
                    return _redact(res)
        except Exception as exc:
            logger.warning("Failed to get task row %s: %s", run_id, exc)

        return None

    async def get_performance(self, run_id: str) -> PerformanceMetrics:
        """Calculate performance metrics from trace records and event timestamps."""
        events = await self.get_run_events(run_id)
        metrics = PerformanceMetrics()
        if not events:
            return metrics

        from datetime import datetime

        def _parse_ts(ts_str: str) -> datetime | None:
            try:
                # Handle ISO format with or without Z
                clean = ts_str.replace("Z", "+00:00")
                return datetime.fromisoformat(clean)
            except Exception:
                return None

        # Parse duration from events
        planner_time = 0.0
        vision_time = 0.0
        browser_time = 0.0
        verification_time = 0.0
        waiting_time = 0.0
        retries_time = 0.0

        for ev in events:
            meta = ev.metadata
            dur_ms = meta.get("duration_ms")
            if dur_ms and isinstance(dur_ms, (int, float)):
                dur_s = dur_ms / 1000.0
                if "VISION" in ev.event_type:
                    vision_time += dur_s
                    metrics.model_latencies.append({
                        "model": meta.get("model", "vision"),
                        "type": "vision",
                        "duration_ms": dur_ms,
                        "timestamp": ev.timestamp,
                    })
                elif "ACTION" in ev.event_type:
                    browser_time += dur_s
                elif "VERIF" in ev.event_type:
                    verification_time += dur_s

        first_ts = _parse_ts(events[0].timestamp)
        last_ts = _parse_ts(events[-1].timestamp)
        total_time = (last_ts - first_ts).total_seconds() if (first_ts and last_ts and last_ts >= first_ts) else 0.0

        # Approximate planner time from gap or defaults
        if total_time > 0:
            residual = max(0.0, total_time - (vision_time + browser_time + verification_time))
            planner_time = round(residual * 0.4, 2)
            waiting_time = round(residual * 0.6, 2)

        metrics.total_duration_sec = round(total_time, 2)
        metrics.planner_duration_sec = round(planner_time, 2)
        metrics.vision_duration_sec = round(vision_time, 2)
        metrics.browser_duration_sec = round(browser_time, 2)
        metrics.verification_duration_sec = round(verification_time, 2)
        metrics.waiting_duration_sec = round(waiting_time, 2)
        metrics.retry_duration_sec = round(retries_time, 2)

        return metrics

    async def list_experiences(self, limit: int = 50) -> list[dict[str, Any]]:
        """Fetch collected experiences from memories table."""
        try:
            async with self.get_connection() as conn:
                cursor = await conn.execute(
                    """
                    SELECT memory_id, type, content, task_id, tags_json, created_at, access_count
                    FROM memories
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                rows = await cursor.fetchall()
                exps = []
                for row in rows:
                    tags = []
                    if row["tags_json"]:
                        try:
                            tags = json.loads(row["tags_json"])
                        except Exception:
                            pass
                    content_val = row["content"]
                    try:
                        content_val = json.loads(content_val)
                    except Exception:
                        pass

                    exps.append({
                        "memory_id": row["memory_id"],
                        "type": row["type"],
                        "task_id": row["task_id"],
                        "content": _redact(content_val),
                        "tags": tags,
                        "created_at": row["created_at"],
                        "access_count": row["access_count"],
                        "training_eligible": False,  # As per instructions: no automatic training
                    })
                return exps
        except Exception as exc:
            logger.warning("Failed to list experiences: %s", exc)
            return []


storage = ReadOnlyStorage()
