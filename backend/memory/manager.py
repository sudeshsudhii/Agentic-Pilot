"""Memory management subsystem for Agentic Pilot."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import chromadb
from pydantic import BaseModel

from backend.config import get_config
from backend.db.database import database, resolve_path


class MemoryRecord(BaseModel):
    """A single episodic or semantic memory."""
    memory_id: str
    type: str
    content: str
    task_id: str | None = None
    tags: list[str] = []
    created_at: str
    last_accessed_at: str
    access_count: int


class MemoryManager:
    """Manages long-term memory via ChromaDB and SQLite."""

    def __init__(self) -> None:
        """Initialize ChromaDB client."""
        db_path = resolve_path(get_config().db_path).parent / "chroma"
        self.chroma = chromadb.PersistentClient(path=str(db_path))
        self.collection = self.chroma.get_or_create_collection("pilot_memories")

    async def store_memory(
        self,
        content: str,
        memory_type: str = "semantic",
        task_id: str | None = None,
        tags: list[str] | None = None,
    ) -> MemoryRecord:
        """Store a new memory in both SQLite and ChromaDB."""
        
        memory_id = str(uuid.uuid4())
        tags = tags or []
        now = datetime.now(UTC).isoformat()
        
        record = MemoryRecord(
            memory_id=memory_id,
            type=memory_type,
            content=content,
            task_id=task_id,
            tags=tags,
            created_at=now,
            last_accessed_at=now,
            access_count=0,
        )
        
        # Store in SQLite
        await database._db().execute(
            """
            INSERT INTO memories (memory_id, type, content, task_id, tags_json, created_at, last_accessed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (memory_id, memory_type, content, task_id, json.dumps(tags), now, now),
        )
        await database._db().commit()
        
        # Store in ChromaDB
        self.collection.add(
            documents=[content],
            metadatas=[{"type": memory_type, "task_id": task_id or ""}],
            ids=[memory_id],
        )
        
        return record

    async def retrieve_relevant(self, query: str, limit: int = 5) -> list[MemoryRecord]:
        """Retrieve relevant memories using vector similarity."""
        
        results = self.collection.query(
            query_texts=[query],
            n_results=limit,
        )
        
        memory_ids = results["ids"][0] if results["ids"] else []
        if not memory_ids:
            return []
            
        # Update access counts and retrieve from SQLite
        retrieved = []
        for mem_id in memory_ids:
            await database._db().execute(
                """
                UPDATE memories 
                SET access_count = access_count + 1, last_accessed_at = CURRENT_TIMESTAMP
                WHERE memory_id = ?
                """,
                (mem_id,)
            )
            cursor = await database._db().execute(
                "SELECT * FROM memories WHERE memory_id = ?",
                (mem_id,)
            )
            row = await cursor.fetchone()
            if row:
                retrieved.append(MemoryRecord(
                    memory_id=row["memory_id"],
                    type=row["type"],
                    content=row["content"],
                    task_id=row["task_id"],
                    tags=json.loads(row["tags_json"] or "[]"),
                    created_at=row["created_at"],
                    last_accessed_at=row["last_accessed_at"],
                    access_count=row["access_count"],
                ))
                
        await database._db().commit()
        return retrieved

    async def summarize_task(self, task_id: str, result: dict, input_text: str) -> None:
        """Create an episodic memory summarizing a completed task."""
        
        success = result.get("success", False)
        content = f"Task: {input_text}. Status: {'Success' if success else 'Failed'}."
        if "error" in result and result["error"]:
            content += f" Error encountered: {result['error']}"
            
        await self.store_memory(
            content=content,
            memory_type="episodic",
            task_id=task_id,
            tags=["task_summary", "success" if success else "failed"]
        )


memory_manager = MemoryManager()
