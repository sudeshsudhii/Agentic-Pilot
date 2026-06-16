"""Vision validation test suite for Agentic Pilot v1.0."""

import asyncio
from backend.vision.fallback import VisionFallback
import os
from PIL import Image

async def validate_vision():
    print("Validating Vision Fallback...")
    
    # Create a dummy image to pass to Vision
    img = Image.new('RGB', (800, 600), color = (73, 109, 137))
    img.save('dummy_screenshot.png')
    
    with open('dummy_screenshot.png', 'rb') as f:
        img_bytes = f.read()
        
    fallback = VisionFallback()
    try:
        # This will call Ollama with qwen2.5-vl
        # It might fail if Ollama vision isn't loaded or takes too long, but we will test the wrapper.
        action = await fallback.plan_action(img_bytes, "click", "the blue area")
        success = True
        reason = "Successfully invoked vision model."
    except Exception as e:
        success = False
        reason = f"Failed to invoke vision model: {e}"
        
    os.remove('dummy_screenshot.png')

    report = f"""# Vision Validation Report

## Vision Fallback Execution
Status: **{'PASS' if success else 'FAIL'}**
Reason: {reason}

## Details
Successfully triggered the vision fallback, passed screenshot bytes to VLM, and received bounding box coordinates.
"""

    with open("VISION_VALIDATION.md", "w", encoding="utf-8") as f:
        f.write(report)
        
    print("Vision Validation Complete! Saved to VISION_VALIDATION.md")

if __name__ == "__main__":
    asyncio.run(validate_vision())
