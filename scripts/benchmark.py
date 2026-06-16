"""Benchmark script for evaluating Agentic Pilot performance."""

import asyncio
import time
import json
from backend.agent.runner import TaskRunner
from backend.db.database import database

async def run_benchmark():
    await database.init()
    runner = TaskRunner(database)
    await runner.start()
    
    tasks = [
        "Go to google.com and search for 'OpenAI'",
        "Navigate to example.com and verify the title",
        "Open hackernews and find the top story"
    ]
    
    results = []
    
    for prompt in tasks:
        print(f"Benchmarking: {prompt}")
        start_time = time.time()
        
        task_id = await runner.submit(prompt)
        
        # Wait for completion
        completed = False
        while not completed:
            await asyncio.sleep(1)
            task = await database.get_task(task_id)
            if task.status in ("completed", "failed", "cancelled"):
                completed = True
                duration = time.time() - start_time
                results.append({
                    "prompt": prompt,
                    "status": task.status,
                    "duration_seconds": round(duration, 2),
                    "error": task.error,
                    "result_json": task.result_json
                })
    
    await runner.shutdown()
    
    print("\nBenchmark Results:")
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    asyncio.run(run_benchmark())
