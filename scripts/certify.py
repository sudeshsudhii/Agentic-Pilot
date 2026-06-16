"""Certification test suite for Agentic Pilot v1.0."""

import asyncio
import json
import os
from pathlib import Path

from backend.config import get_config
from backend.db.database import resolve_path

from backend.agent.runner import TaskRunner
from backend.db.database import database

async def certify():
    await database.connect()
    runner = TaskRunner(database)
    await runner.start()

    tasks = [
        {"name": "Test 1: Open Google", "prompt": "Open google.com"},
        {"name": "Test 2: Search AI", "prompt": "Search Google for 'Artificial Intelligence'"},
        {"name": "Test 3: Extract Wikipedia", "prompt": "Go to wikipedia.org and search for 'Alan Turing'"},
        {"name": "Test 4: GitHub extraction", "prompt": "Navigate to github.com"},
        {"name": "Test 5: Take Screenshot", "prompt": "Go to example.com and capture a screenshot"}
    ]

    results = []
    
    for task_meta in tasks:
        print(f"Running {task_meta['name']}...")
        task_id = await runner.submit(task_meta["prompt"])
        
        while True:
            await asyncio.sleep(2)
            task = await database.get_task(task_id)
            if task.status in ["completed", "failed", "cancelled"]:
                break
                
        # Audit evidence
        evidence_dir = resolve_path(get_config().log_dir) / "evidence" / task_id
        has_screenshot = evidence_dir.exists() and len(list(evidence_dir.glob("*.png"))) > 0
        has_trace = (evidence_dir / "trace.json").exists()
        
        success = task.status == "completed" and has_screenshot and has_trace
        results.append({
            "name": task_meta["name"],
            "status": "PASS" if success else "FAIL",
            "reason": task.error if not success else "Verified execution and evidence generation."
        })

    await runner.shutdown()

    report = "# Agentic Pilot v1.0 Certification Report\n\n"
    for res in results:
        report += f"## {res['name']}\nStatus: **{res['status']}**\nReason: {res['reason']}\n\n"

    with open("CERTIFICATION_REPORT.md", "w", encoding="utf-8") as f:
        f.write(report)
        
    print("\nCertification Complete! Saved to CERTIFICATION_REPORT.md")

if __name__ == "__main__":
    asyncio.run(certify())
