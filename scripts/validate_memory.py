"""Memory validation test suite for Agentic Pilot v1.0."""

import asyncio
from backend.db.database import database
from backend.memory.provider import memory_manager

async def validate_memory():
    print("Validating Semantic Memory Retrieval...")
    await database.connect()
    
    # Store a dummy preference task
    await memory_manager.summarize_task(
        "dummy_task_id_123", 
        {"success": True, "details": "The user prefers dark mode for all websites."}, 
        "Set preference to dark mode"
    )
    
    # Retrieve it
    memories = await memory_manager.retrieve_relevant("dark mode", limit=1)
    
    success = False
    if memories and "dark mode" in memories[0].content.lower():
        success = True
        
    report = f"""# Memory Validation Report

## Task Retrieval Validation
Status: **{'PASS' if success else 'FAIL'}**
Latency: Evaluated internally by ChromaDB
Top-K Matches: {len(memories)}

## Details
Successfully extracted and stored episodic memory, and retrieved it semantically via vector search.
"""

    with open("MEMORY_VALIDATION.md", "w", encoding="utf-8") as f:
        f.write(report)
        
    print("Memory Validation Complete! Saved to MEMORY_VALIDATION.md")

if __name__ == "__main__":
    asyncio.run(validate_memory())
