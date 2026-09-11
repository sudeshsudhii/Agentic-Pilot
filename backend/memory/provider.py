"""Memory provider abstractions for Agentic Pilot."""

from __future__ import annotations
import asyncio
import json
import uuid
from abc import ABC, abstractmethod
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

class MemoryProvider(ABC):
    """Base class for memory providers."""
    
    @abstractmethod
    async def store_memory(self, content: str, memory_type: str = "semantic", task_id: str | None = None, tags: list[str] | None = None) -> MemoryRecord | None:
        pass
        
    @abstractmethod
    async def retrieve_relevant(self, query: str, limit: int = 5) -> list[MemoryRecord]:
        pass
        
    @abstractmethod
    async def summarize_task(self, task_id: str, result: dict, input_text: str) -> None:
        pass

    @abstractmethod
    async def store_strategy(self, task_id: str, goal: str, strategy: dict, outcome: str = "success") -> MemoryRecord | None:
        pass

    @abstractmethod
    async def store_failure(self, task_id: str, goal: str, failure: dict, diagnosis: str) -> MemoryRecord | None:
        pass

    @abstractmethod
    async def retrieve_strategies(self, query: str, limit: int = 3) -> list[MemoryRecord]:
        pass

class ChromaProvider(MemoryProvider):
    """ChromaDB implementation of MemoryProvider."""

    def __init__(self) -> None:
        db_path = resolve_path(get_config().db_path).parent / "chroma"
        self.chroma = chromadb.PersistentClient(path=str(db_path))
        self.collection = self.chroma.get_or_create_collection("pilot_memories")

    async def store_memory(self, content: str, memory_type: str = "semantic", task_id: str | None = None, tags: list[str] | None = None) -> MemoryRecord | None:
        if not get_config().enable_memory:
            return None

        memory_id = str(uuid.uuid4())
        tags = tags or []
        now = datetime.now(UTC).isoformat()
        
        record = MemoryRecord(
            memory_id=memory_id, type=memory_type, content=content, task_id=task_id, tags=tags,
            created_at=now, last_accessed_at=now, access_count=0,
        )
        
        await database._db().execute(
            "INSERT INTO memories (memory_id, type, content, task_id, tags_json, created_at, last_accessed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (memory_id, memory_type, content, task_id, json.dumps(tags), now, now),
        )
        await database._db().commit()
        
        await asyncio.to_thread(
            self.collection.add,
            documents=[content],
            metadatas=[{"type": memory_type, "task_id": task_id or ""}],
            ids=[memory_id],
        )
        return record

    async def retrieve_relevant(self, query: str, limit: int = 5) -> list[MemoryRecord]:
        if not get_config().enable_memory:
            return []

        try:
            results = await asyncio.to_thread(self.collection.query, query_texts=[query], n_results=limit)
        except Exception:
            return []
        
        memory_ids = results["ids"][0] if results["ids"] else []
        if not memory_ids:
            return []
            
        retrieved = []
        for mem_id in memory_ids:
            await database._db().execute(
                "UPDATE memories SET access_count = access_count + 1, last_accessed_at = CURRENT_TIMESTAMP WHERE memory_id = ?",
                (mem_id,)
            )
            cursor = await database._db().execute("SELECT * FROM memories WHERE memory_id = ?", (mem_id,))
            row = await cursor.fetchone()
            if row:
                retrieved.append(MemoryRecord(
                    memory_id=row["memory_id"], type=row["type"], content=row["content"], task_id=row["task_id"],
                    tags=json.loads(row["tags_json"] or "[]"), created_at=row["created_at"],
                    last_accessed_at=row["last_accessed_at"], access_count=row["access_count"],
                ))
                
        await database._db().commit()
        return retrieved

    async def summarize_task(self, task_id: str, result: dict, input_text: str) -> None:
        if not get_config().enable_memory:
            return

        success = result.get("success", False)
        content = f"Task: {input_text}. Status: {'Success' if success else 'Failed'}."
        if "error" in result and result["error"]:
            content += f" Error encountered: {result['error']}"
            
        await self.store_memory(
            content=content, memory_type="episodic", task_id=task_id, tags=["task_summary", "success" if success else "failed"]
        )

    async def store_strategy(self, task_id: str, goal: str, strategy: dict, outcome: str = "success") -> MemoryRecord | None:
        """Store an effective execution strategy for cross-session reuse (R11)."""
        if not get_config().enable_memory:
            return None

        content = f"Strategy for '{goal}': {json.dumps(strategy)}. Outcome: {outcome}."
        tags = ["strategy", outcome, f"goal:{goal[:30]}"]
        return await self.store_memory(
            content=content,
            memory_type="strategy",
            task_id=task_id,
            tags=tags,
        )

    async def store_failure(self, task_id: str, goal: str, failure: dict, diagnosis: str) -> MemoryRecord | None:
        """Store a failure diagnosis to avoid repeating known failed strategies (R11)."""
        if not get_config().enable_memory:
            return None

        content = f"Failure on '{goal}': Diagnosis: {diagnosis}. Details: {json.dumps(failure)}."
        tags = ["failure_pattern", f"goal:{goal[:30]}"]
        return await self.store_memory(
            content=content,
            memory_type="failure_pattern",
            task_id=task_id,
            tags=tags,
        )

    async def retrieve_strategies(self, query: str, limit: int = 3) -> list[MemoryRecord]:
        """Retrieve relevant past strategies and failure patterns for planning (R11)."""
        if not get_config().enable_memory:
            return []

        search_query = f"strategy or failure for {query}"
        return await self.retrieve_relevant(search_query, limit=limit)

# Factory instance
memory_manager: MemoryProvider = ChromaProvider()

