"""Pytest suite for live Windows desktop automation and stored test data validation."""

import json
from pathlib import Path
import pytest

from scripts.run_live_desktop_test import LiveDesktopTestRunner, PROJECT_ROOT


@pytest.mark.asyncio
async def test_live_desktop_automation_execution():
    """Execute live desktop automation scenario on Windows and assert success."""
    runner = LiveDesktopTestRunner()
    manifest = await runner.run()

    assert manifest["status"] == "PASSED", f"Live test run failed: {manifest.get('error')}"
    assert manifest["assertions"]["failed"] == 0, f"Some assertions failed: {manifest['assertions']}"
    assert manifest["assertions"]["passed"] >= 4, "Expected at least 4 passed deterministic assertions"

    # Verify all steps succeeded
    for step in manifest.get("steps", []):
        assert step["status"] == "PASS", f"Step {step['name']} did not pass: {step['details']}"


def test_stored_test_data_files_exist_and_valid():
    """Verify that the stored test data artifacts exist, are non-empty, and follow schemas."""
    data_dir = PROJECT_ROOT / "tests" / "data" / "live_test_runs" / "latest"
    assert data_dir.exists(), f"Stored test data directory does not exist: {data_dir}"

    # 1. manifest.json
    manifest_path = data_dir / "manifest.json"
    assert manifest_path.exists(), "manifest.json missing"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "PASSED"
    assert "os_environment" in manifest
    assert "metrics" in manifest

    # 2. trace.json
    trace_path = data_dir / "trace.json"
    assert trace_path.exists(), "trace.json missing"
    traces = json.loads(trace_path.read_text(encoding="utf-8"))
    assert isinstance(traces, list) and len(traces) >= 5, "trace.json has too few events"

    # 3. verifications.json
    verif_path = data_dir / "verifications.json"
    assert verif_path.exists(), "verifications.json missing"
    verifs = json.loads(verif_path.read_text(encoding="utf-8"))
    assert isinstance(verifs, list) and len(verifs) >= 4, "verifications.json missing records"
    for v in verifs:
        assert v.get("verified") is True, f"Verification failed in test data: {v}"

    # 4. uia_tree.json
    uia_path = data_dir / "uia_tree.json"
    assert uia_path.exists(), "uia_tree.json missing"
    uia_elements = json.loads(uia_path.read_text(encoding="utf-8"))
    assert isinstance(uia_elements, list) and len(uia_elements) > 0, "No UIA elements stored"
    assert "role" in uia_elements[0]
    assert "bbox" in uia_elements[0]

    # 5. execution_records.json
    records_path = data_dir / "execution_records.json"
    assert records_path.exists(), "execution_records.json missing"
    records = json.loads(records_path.read_text(encoding="utf-8"))
    assert isinstance(records, list) and len(records) > 0, "No execution records stored"

    # 6. summary.md
    summary_path = data_dir / "summary.md"
    assert summary_path.exists(), "summary.md missing"
    assert len(summary_path.read_text(encoding="utf-8")) > 100, "summary.md too short"

    # 7. screenshots directory
    screens_dir = data_dir / "screenshots"
    assert screens_dir.exists(), "screenshots/ directory missing"
    screenshots = list(screens_dir.glob("*.png"))
    assert len(screenshots) >= 3, f"Expected at least 3 screenshots, found {len(screenshots)}"
    for s in screenshots:
        assert s.stat().st_size > 0, f"Screenshot {s.name} is empty (0 bytes)"
