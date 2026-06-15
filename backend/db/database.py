"""SQLite connection management and migrations for Pilot."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiosqlite

from backend.config import get_config
from backend.db.models import ApprovalRecord, EventRecord, TaskRecord


def resolve_path(path: str) -> Path:
    """Expand a configured local path and ensure its parent exists."""

    resolved = Path(path).expanduser()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


class Database:
    """Small async SQLite wrapper with typed record helpers."""

    def __init__(self, path: str) -> None:
        """Create the database wrapper for a configured SQLite path."""

        self.path = resolve_path(path)
        self.connection: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Open the SQLite connection and run idempotent migrations."""

        self.connection = await aiosqlite.connect(self.path)
        self.connection.row_factory = aiosqlite.Row
        await self.connection.execute("PRAGMA foreign_keys = ON")
        await self._migrate()

    async def close(self) -> None:
        """Close the active SQLite connection if one is open."""

        if self.connection is not None:
            await self.connection.close()
            self.connection = None

    async def _migrate(self) -> None:
        """Create all tables required by the current backend version."""

        db = self._db()
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                input_text TEXT NOT NULL,
                status TEXT NOT NULL,
                risk_level TEXT,
                parsed_intent_json TEXT,
                result_json TEXT,
                error TEXT,
                approval_id TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS task_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                type TEXT NOT NULL,
                message TEXT NOT NULL,
                payload_json TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS approvals (
                approval_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                prompt TEXT NOT NULL,
                status TEXT NOT NULL,
                response TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                decided_at TEXT,
                FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sessions (
                site TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                expires_at TEXT
            );
            """
        )
        await db.commit()

    def _db(self) -> aiosqlite.Connection:
        """Return the active connection or raise a clear startup error."""

        if self.connection is None:
            raise RuntimeError("Database is not connected")
        return self.connection

    async def create_task(self, task_id: str, input_text: str) -> TaskRecord:
        """Insert a new queued task and return it."""

        db = self._db()
        await db.execute(
            """
            INSERT INTO tasks (task_id, input_text, status)
            VALUES (?, ?, ?)
            """,
            (task_id, input_text, "queued"),
        )
        await db.commit()
        task = await self.get_task(task_id)
        if task is None:
            raise RuntimeError("Task insert failed")
        return task

    async def update_task(self, task_id: str, **fields: Any) -> TaskRecord:
        """Update whitelisted task columns and return the updated task."""

        allowed = {
            "status",
            "risk_level",
            "parsed_intent_json",
            "result_json",
            "error",
            "approval_id",
            "completed_at",
        }
        updates: list[str] = []
        values: list[Any] = []
        for key, value in fields.items():
            if key not in allowed:
                raise ValueError("Unsupported task field: " + key)
            updates.append(key + " = ?")
            values.append(value)

        updates.append("updated_at = CURRENT_TIMESTAMP")
        values.append(task_id)
        sql = "UPDATE tasks SET " + ", ".join(updates) + " WHERE task_id = ?"
        await self._db().execute(sql, values)
        await self._db().commit()
        task = await self.get_task(task_id)
        if task is None:
            raise RuntimeError("Task update failed")
        return task

    async def get_task(self, task_id: str) -> TaskRecord | None:
        """Return one task by id, or None when it does not exist."""

        cursor = await self._db().execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
        row = await cursor.fetchone()
        return self._task_from_row(row) if row else None

    async def list_tasks(self, limit: int = 50) -> list[TaskRecord]:
        """Return the most recent tasks."""

        cursor = await self._db().execute(
            "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [self._task_from_row(row) for row in rows]

    async def add_event(
        self,
        task_id: str,
        event_type: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> EventRecord:
        """Persist a task event and return it."""

        cursor = await self._db().execute(
            """
            INSERT INTO task_events (task_id, type, message, payload_json)
            VALUES (?, ?, ?, ?)
            """,
            (task_id, event_type, message, _to_json(payload)),
        )
        await self._db().commit()
        event_id = cursor.lastrowid
        cursor = await self._db().execute("SELECT * FROM task_events WHERE id = ?", (event_id,))
        row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("Event insert failed")
        return self._event_from_row(row)

    async def list_events(self, task_id: str, after_id: int = 0) -> list[EventRecord]:
        """Return events for a task after a previously seen event id."""

        cursor = await self._db().execute(
            """
            SELECT * FROM task_events
            WHERE task_id = ? AND id > ?
            ORDER BY id ASC
            """,
            (task_id, after_id),
        )
        rows = await cursor.fetchall()
        return [self._event_from_row(row) for row in rows]

    async def create_approval(
        self,
        approval_id: str,
        task_id: str,
        risk_level: str,
        prompt: str,
    ) -> ApprovalRecord:
        """Create a pending approval request."""

        await self._db().execute(
            """
            INSERT INTO approvals (approval_id, task_id, risk_level, prompt, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (approval_id, task_id, risk_level, prompt, "pending"),
        )
        await self._db().commit()
        approval = await self.get_approval(approval_id)
        if approval is None:
            raise RuntimeError("Approval insert failed")
        return approval

    async def respond_approval(self, approval_id: str, decision: str) -> ApprovalRecord:
        """Mark an approval as approved or rejected."""

        status = "approved" if decision == "approved" else "rejected"
        await self._db().execute(
            """
            UPDATE approvals
            SET status = ?, response = ?, decided_at = CURRENT_TIMESTAMP
            WHERE approval_id = ?
            """,
            (status, decision, approval_id),
        )
        await self._db().commit()
        approval = await self.get_approval(approval_id)
        if approval is None:
            raise RuntimeError("Approval not found")
        return approval

    async def get_approval(self, approval_id: str) -> ApprovalRecord | None:
        """Return one approval request by id."""

        cursor = await self._db().execute("SELECT * FROM approvals WHERE approval_id = ?", (approval_id,))
        row = await cursor.fetchone()
        return self._approval_from_row(row) if row else None

    async def list_pending_approvals(self) -> list[ApprovalRecord]:
        """Return all approval requests still waiting for user action."""

        cursor = await self._db().execute(
            "SELECT * FROM approvals WHERE status = ? ORDER BY created_at DESC",
            ("pending",),
        )
        rows = await cursor.fetchall()
        return [self._approval_from_row(row) for row in rows]

    async def get_setting(self, key: str, default: str | None = None) -> str | None:
        """Return a setting string value or the provided default."""

        cursor = await self._db().execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cursor.fetchone()
        return str(row["value"]) if row else default

    async def set_setting(self, key: str, value: str) -> None:
        """Upsert a setting string value."""

        await self._db().execute(
            """
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            """,
            (key, value),
        )
        await self._db().commit()

    async def count_tasks(self) -> int:
        """Return the total number of stored tasks."""

        cursor = await self._db().execute("SELECT COUNT(*) AS count FROM tasks")
        row = await cursor.fetchone()
        return int(row["count"]) if row else 0

    def _task_from_row(self, row: aiosqlite.Row) -> TaskRecord:
        """Convert a SQLite row into a task record."""

        return TaskRecord(
            task_id=row["task_id"],
            input_text=row["input_text"],
            status=row["status"],
            risk_level=row["risk_level"],
            parsed_intent=_from_json(row["parsed_intent_json"]),
            result=_from_json(row["result_json"]),
            error=row["error"],
            approval_id=row["approval_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=row["completed_at"],
        )

    def _event_from_row(self, row: aiosqlite.Row) -> EventRecord:
        """Convert a SQLite row into a task event record."""

        return EventRecord(
            id=int(row["id"]),
            task_id=row["task_id"],
            type=row["type"],
            message=row["message"],
            payload=_from_json(row["payload_json"]),
            created_at=row["created_at"],
        )

    def _approval_from_row(self, row: aiosqlite.Row) -> ApprovalRecord:
        """Convert a SQLite row into an approval record."""

        return ApprovalRecord(
            approval_id=row["approval_id"],
            task_id=row["task_id"],
            risk_level=row["risk_level"],
            prompt=row["prompt"],
            status=row["status"],
            response=row["response"],
            created_at=row["created_at"],
            decided_at=row["decided_at"],
        )


def _to_json(value: dict[str, Any] | None) -> str | None:
    """Serialize optional dictionaries for SQLite storage."""

    return json.dumps(value) if value is not None else None


def _from_json(value: str | None) -> dict[str, Any] | None:
    """Deserialize optional dictionaries from SQLite storage."""

    return json.loads(value) if value else None


database = Database(get_config().db_path)
