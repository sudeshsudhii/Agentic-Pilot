"""Unified Context Builder for Agentic Pilot.

Transforms retrieved knowledge and episodic memory into structured,
token-budgeted, deduplicated, and model-specific prompt context.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from pydantic import BaseModel, Field

from backend.config import get_config
from backend.rag.models import RetrievedChunk
from backend.rag.security import format_untrusted_knowledge_context

logger = logging.getLogger("pilot.rag.context_builder")


class BuiltContext(BaseModel):
    """Result of context assembly and compression."""

    knowledge_text: str = ""
    memory_text: str = ""
    combined_prompt_context: str = ""
    estimated_tokens: int = 0
    chunks_included: int = 0
    memories_included: int = 0
    is_truncated: bool = False


class ContextBuilder:
    """Constructs model-specific prompt context with compression and token budgeting."""

    def __init__(self, token_budget: int | None = None) -> None:
        self._default_budget = token_budget

    def _estimate_tokens(self, text: str) -> int:
        """Heuristic token estimation (~4 characters per token)."""
        return max(1, len(text) // 4)

    def _deduplicate_chunks(self, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """Remove near-identical chunks based on normalized content."""
        seen: set[str] = set()
        unique: list[RetrievedChunk] = []
        for c in chunks:
            norm = re.sub(r"\s+", " ", c.content[:120].strip().lower())
            if norm not in seen:
                seen.add(norm)
                unique.append(c)
        return unique

    def _deduplicate_memories(self, memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Remove duplicate episodic memories."""
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for m in memories:
            content = str(m.get("content", ""))
            norm = re.sub(r"\s+", " ", content[:100].strip().lower())
            if norm not in seen:
                seen.add(norm)
                unique.append(m)
        return unique

    def build_context(
        self,
        retrieved_knowledge: list[dict[str, Any]] | None,
        retrieved_memories: list[dict[str, Any]] | None,
        model_role: str = "general",
        token_budget: int | None = None,
    ) -> BuiltContext:
        """Assemble, compress, and format context within token budget."""
        config = get_config()
        budget = token_budget or self._default_budget or getattr(config, "task_context_token_budget", 1500)

        # 1. Parse & Deduplicate Knowledge Chunks
        raw_chunks: list[RetrievedChunk] = []
        if retrieved_knowledge:
            for k in retrieved_knowledge:
                if isinstance(k, RetrievedChunk):
                    raw_chunks.append(k)
                elif isinstance(k, dict):
                    try:
                        chunk_dict = {
                            "document_id": k.get("document_id", "doc-1"),
                            "chunk_id": k.get("chunk_id", "chunk-1"),
                            "content": k.get("content", ""),
                            "score": float(k.get("score", 0.9)),
                            "source": k.get("source", "knowledge_base"),
                            "section": k.get("section"),
                            "document_type": k.get("document_type", "text"),
                            "metadata": k.get("metadata", {}),
                        }
                        raw_chunks.append(RetrievedChunk.model_validate(chunk_dict))
                    except Exception as err:
                        logger.debug("Failed to parse chunk dict: %s", err)
        deduped_chunks = self._deduplicate_chunks(raw_chunks)

        # 2. Parse & Deduplicate Memories
        deduped_memories = self._deduplicate_memories(retrieved_memories or [])

        # 3. Apply Token Budgeting & Compression
        allocated_knowledge_tokens = int(budget * 0.65)
        allocated_memory_tokens = budget - allocated_knowledge_tokens

        # Format Memory Context first
        memory_lines: list[str] = []
        current_mem_tokens = 0
        memories_count = 0
        for m in deduped_memories:
            prefix = "[Past Strategy]" if m.get("type") == "strategy" else "[Past Experience]"
            line = f"- {prefix} {m.get('content', '').strip()}"
            line_tokens = self._estimate_tokens(line)
            if current_mem_tokens + line_tokens > allocated_memory_tokens:
                break
            memory_lines.append(line)
            current_mem_tokens += line_tokens
            memories_count += 1

        memory_text = ""
        if memory_lines:
            memory_text = "=== PAST EXECUTION EXPERIENCE ===\n" + "\n".join(memory_lines) + "\n" + ("=" * 35)

        # Format Knowledge Context according to model role
        selected_chunks: list[RetrievedChunk] = []
        current_know_tokens = 0
        is_truncated = False
        for c in deduped_chunks:
            c_tokens = self._estimate_tokens(c.content)
            if current_know_tokens + c_tokens > allocated_knowledge_tokens:
                is_truncated = True
                break
            selected_chunks.append(c)
            current_know_tokens += c_tokens

        knowledge_text = ""
        if selected_chunks:
            base_knowledge = format_untrusted_knowledge_context(selected_chunks)

            role_norm = model_role.lower()
            if role_norm in ("coding", "coder"):
                knowledge_text = (
                    "=== [CODING SPECIALIST CONTEXT: LOCAL DOCUMENTATION & API SYNTAX] ===\n"
                    f"{base_knowledge}\n"
                    "=== [END CODE KNOWLEDGE CONTEXT] ==="
                )
            elif role_norm == "vision":
                knowledge_text = (
                    "=== [VISION SPECIALIST CONTEXT: UI & VISUAL LAYOUT GUIDES] ===\n"
                    f"{base_knowledge}\n"
                    "=== [END VISUAL CONTEXT] ==="
                )
            elif role_norm in ("reasoning", "recovery", "planner"):
                knowledge_text = (
                    "=== [REASONING/RECOVERY CONTEXT: VERIFIED PROCEDURAL INVARIANTS] ===\n"
                    f"{base_knowledge}\n"
                    "=== [END INVARIANTS CONTEXT] ==="
                )
            elif role_norm == "lightweight":
                condensed = "\n".join(
                    f"• {c.source}: {c.content[:120]}..."
                    for c in selected_chunks[:2]
                )
                knowledge_text = f"[Compact Knowledge]:\n{condensed}"
            else:
                knowledge_text = base_knowledge

        # Combined Context
        parts = [p for p in (knowledge_text, memory_text) if p]
        combined = "\n\n".join(parts)
        total_tokens = self._estimate_tokens(combined)

        return BuiltContext(
            knowledge_text=knowledge_text,
            memory_text=memory_text,
            combined_prompt_context=combined,
            estimated_tokens=total_tokens,
            chunks_included=len(selected_chunks),
            memories_included=memories_count,
            is_truncated=is_truncated,
        )


# Global singleton builder
context_builder = ContextBuilder()
