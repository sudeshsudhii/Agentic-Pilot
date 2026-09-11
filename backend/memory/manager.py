"""Memory management compatibility re-export for Agentic Pilot.

This module re-exports the canonical implementation from backend.memory.provider (DEC-005)
to prevent duplicate implementations while maintaining full backwards compatibility.
"""

from backend.memory.provider import (
    ChromaProvider,
    MemoryProvider,
    MemoryRecord,
    memory_manager,
)

# Alias for backwards compatibility
MemoryManager = ChromaProvider

__all__ = [
    "ChromaProvider",
    "MemoryManager",
    "MemoryProvider",
    "MemoryRecord",
    "memory_manager",
]
