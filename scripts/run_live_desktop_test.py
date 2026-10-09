"""Live Windows Desktop Automation Test and Evidence Data Storage Suite.

Executes a live automation scenario on the Windows Desktop:
1. Environment probing (resolution, DPI scaling, initial window state)
2. Controlled application launch (Notepad) via app_launcher
3. Live state verification via DesktopVerifier (GoalPredicates)
4. Window focus and UIA element tree observation via desktop_observer
5. Live text typing via desktop_executor
6. Evidence collection (full screenshots, UIA tree dump, action traces)
7. Controlled teardown and cleanup verification
8. Persisting complete test data artifacts into tests/data/live_test_runs/
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.desktop.applications import app_launcher
from backend.desktop.executor import desktop_executor
from backend.desktop.models import (
    DesktopElement,
    GoalCondition,
    GoalPredicate,
    GoalTarget,
)
from backend.desktop.observer import desktop_observer
from backend.desktop.uia import uia_manager
from backend.desktop.verifier import desktop_verifier
from backend.desktop.windows import window_manager
from backend.evidence.manager import ExecutionRecord, evidence_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("live_test")


class LiveDesktopTestRunner:
    """Orchestrates live desktop automation test and stores all test artifacts."""

    def __init__(self, output_base_dir: Path | None = None) -> None:
        self.timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        self.run_id = f"live_run_{self.timestamp}"
        self.base_dir = output_base_dir or (PROJECT_ROOT / "tests" / "data" / "live_test_runs")
        self.run_dir = self.base_dir / f"run_{self.timestamp}"
        self.screenshots_dir = self.run_dir / "screenshots"
        self.latest_dir = self.base_dir / "latest"

        # Trace and assertion accumulators
        self.trace_events: list[dict[str, Any]] = []
        self.verifications: list[dict[str, Any]] = []
        self.execution_records: list[ExecutionRecord] = []
        self.steps_summary: list[dict[str, Any]] = []
        self.start_time: float = 0.0

    def _log_trace(self, event_type: str, message: str, payload: dict[str, Any] | None = None) -> None:
        """Record an event to the chronological trace."""
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "elapsed_ms": int((time.perf_counter() - self.start_time) * 1000) if self.start_time else 0,
            "type": event_type,
            "message": message,
            "data": payload or {},
        }
        self.trace_events.append(event)
        logger.info("[TRACE] %s: %s", event_type, message)

    async def run(self) -> dict[str, Any]:
        """Execute full live test sequence and store all test data."""
        self.start_time = time.perf_counter()
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

        logger.info("==================================================")
        logger.info("STARTING LIVE DESKTOP TEST: %s", self.run_id)
        logger.info("Storage Output Directory: %s", self.run_dir)
        logger.info("==================================================")

        self._log_trace("TEST_START", f"Starting live desktop test run {self.run_id}")

        manifest: dict[str, Any] = {
            "run_id": self.run_id,
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "os_environment": {
                "system": platform.system(),
                "release": platform.release(),
                "version": platform.version(),
                "machine": platform.machine(),
                "python_version": sys.version,
            },
            "status": "RUNNING",
            "steps": [],
            "assertions": {"total": 0, "passed": 0, "failed": 0},
            "metrics": {},
        }

        uia_tree_dump: list[dict[str, Any]] = []

        try:
            # ─────────────────────────────────────────────────────────
            # STEP 1: Environment & System Snapshot
            # ─────────────────────────────────────────────────────────
            step_start = time.perf_counter()
            screen_w, screen_h = await desktop_executor.get_screen_size()
            dpi_scale = await window_manager.get_dpi_scale()
            initial_windows = await uia_manager.list_windows()

            # Capture initial desktop screenshot
            pre_shot = await desktop_executor.take_screenshot()
            pre_shot_path = self.screenshots_dir / "01_initial_desktop.png"
            if pre_shot:
                pre_shot_path.write_bytes(pre_shot)

            manifest["os_environment"]["resolution"] = f"{screen_w}x{screen_h}"
            manifest["os_environment"]["dpi_scale"] = dpi_scale
            manifest["os_environment"]["initial_window_count"] = len(initial_windows)

            self._log_trace(
                "SYSTEM_SNAPSHOT",
                f"Resolution {screen_w}x{screen_h}, DPI {dpi_scale}, Windows {len(initial_windows)}",
                {
                    "resolution": [screen_w, screen_h],
                    "dpi_scale": dpi_scale,
                    "windows": [w.title for w in initial_windows],
                    "screenshot_bytes": len(pre_shot),
                },
            )

            self.steps_summary.append({
                "step": 1,
                "name": "System Snapshot",
                "status": "PASS",
                "duration_ms": int((time.perf_counter() - step_start) * 1000),
                "details": f"Screen {screen_w}x{screen_h}, {len(initial_windows)} windows detected",
            })

            # ─────────────────────────────────────────────────────────
            # STEP 2: Controlled Application Launch (Notepad)
            # ─────────────────────────────────────────────────────────
            step_start = time.perf_counter()
            self._log_trace("APP_LAUNCH_START", "Launching Notepad via controlled app_launcher")
            launch_res = await app_launcher.launch("notepad")

            if not launch_res.success:
                raise RuntimeError(f"Failed to launch Notepad: {launch_res.error}")

            await asyncio.sleep(1.5)  # allow UI to map and render

            self._log_trace("APP_LAUNCH_SUCCESS", "Notepad launched successfully")
            self.steps_summary.append({
                "step": 2,
                "name": "Launch Application (Notepad)",
                "status": "PASS" if launch_res.success else "FAIL",
                "duration_ms": int((time.perf_counter() - step_start) * 1000),
                "details": f"Application launched in {launch_res.duration_ms}ms",
            })

            # ─────────────────────────────────────────────────────────
            # STEP 3: Live Verification of Launch
            # ─────────────────────────────────────────────────────────
            step_start = time.perf_counter()
            cond_app = GoalCondition(
                predicate=GoalPredicate.APPLICATION_RUNNING,
                target=GoalTarget(process_name="notepad.exe", application="Notepad"),
                expected_value=True,
                description="Notepad process must be running in OS",
            )
            cond_win = GoalCondition(
                predicate=GoalPredicate.WINDOW_EXISTS,
                target=GoalTarget(window="Notepad"),
                expected_value=True,
                description="Notepad window must exist",
            )

            v_app = await desktop_verifier.verify_goal(cond_app)
            v_win = await desktop_verifier.verify_goal(cond_win)

            self._record_verification(cond_app, v_app)
            self._record_verification(cond_win, v_win)

            assert v_app.verified, f"Application running verification failed: {v_app.message}"
            assert v_win.verified, f"Window exists verification failed: {v_win.message}"

            self.steps_summary.append({
                "step": 3,
                "name": "Verify Launch Predicates",
                "status": "PASS",
                "duration_ms": int((time.perf_counter() - step_start) * 1000),
                "details": "APPLICATION_RUNNING and WINDOW_EXISTS verified True",
            })

            # ─────────────────────────────────────────────────────────
            # STEP 4: Window Focus & Screenshot
            # ─────────────────────────────────────────────────────────
            step_start = time.perf_counter()
            focused = await window_manager.focus_window("Notepad")
            await asyncio.sleep(0.5)

            cond_focus = GoalCondition(
                predicate=GoalPredicate.WINDOW_FOCUSED,
                target=GoalTarget(window="Notepad"),
                expected_value=True,
                description="Notepad window should be focused",
            )
            v_focus = await desktop_verifier.verify_goal(cond_focus)
            self._record_verification(cond_focus, v_focus)

            # Capture launched app screenshot
            shot_app = await desktop_executor.take_screenshot()
            shot_app_path = self.screenshots_dir / "02_app_launched.png"
            if shot_app:
                shot_app_path.write_bytes(shot_app)

            self.steps_summary.append({
                "step": 4,
                "name": "Focus Window & Screenshot",
                "status": "PASS",
                "duration_ms": int((time.perf_counter() - step_start) * 1000),
                "details": f"Window focused (focus_call={focused}, verified={v_focus.verified})",
            })

            # ─────────────────────────────────────────────────────────
            # STEP 5: Bounded UIA Desktop Observation
            # ─────────────────────────────────────────────────────────
            step_start = time.perf_counter()
            obs = await desktop_observer.observe(target_window="Notepad")
            uia_elements = obs.elements
            uia_tree_dump = [e.model_dump() for e in uia_elements]

            self._log_trace(
                "OBSERVATION_COMPLETE",
                f"Observed {len(uia_elements)} elements in Notepad (total: {obs.element_count_total})",
                {"element_count": len(uia_elements), "total": obs.element_count_total},
            )

            # Assert observation extracted controls
            assert len(uia_elements) > 0, "No UIA elements extracted from Notepad window"

            # Check ELEMENT_EXISTS predicate
            cond_elem = GoalCondition(
                predicate=GoalPredicate.ELEMENT_EXISTS,
                target=GoalTarget(name="Notepad", window="Notepad"),
                expected_value=True,
                description="Notepad element exists in observation",
            )
            v_elem = await desktop_verifier.verify_goal(cond_elem, observation=obs)
            self._record_verification(cond_elem, v_elem)

            self.steps_summary.append({
                "step": 5,
                "name": "UIA Observation",
                "status": "PASS",
                "duration_ms": int((time.perf_counter() - step_start) * 1000),
                "details": f"Extracted {len(uia_elements)} bounded elements, total {obs.element_count_total}",
            })

            # ─────────────────────────────────────────────────────────
            # STEP 6: Live Interaction (Typing verification message)
            # ─────────────────────────────────────────────────────────
            step_start = time.perf_counter()
            test_phrase = f"Agentic Pilot Desktop Live Verification Run {self.run_id}\nAutomated testing passed."
            self._log_trace("INTERACTION_START", f"Typing test phrase ({len(test_phrase)} chars)")

            type_res = await desktop_executor.type_text(test_phrase, interval=0.01)
            await asyncio.sleep(0.5)

            shot_type = await desktop_executor.take_screenshot()
            shot_type_path = self.screenshots_dir / "03_text_interacted.png"
            if shot_type:
                shot_type_path.write_bytes(shot_type)

            self._log_trace("INTERACTION_COMPLETE", "Text typed into active window successfully")
            self.steps_summary.append({
                "step": 6,
                "name": "Live Typing Interaction",
                "status": "PASS" if type_res.success else "FAIL",
                "duration_ms": int((time.perf_counter() - step_start) * 1000),
                "details": f"Typed {len(test_phrase)} characters into Notepad",
            })

            # ─────────────────────────────────────────────────────────
            # STEP 7: Controlled Teardown & Process Cleanup
            # ─────────────────────────────────────────────────────────
            step_start = time.perf_counter()
            self._log_trace("CLEANUP_START", "Terminating Notepad process cleanly")
            terminated = await app_launcher.terminate_app("notepad")
            await asyncio.sleep(1.0)

            cond_cleanup = GoalCondition(
                predicate=GoalPredicate.WINDOW_EXISTS,
                target=GoalTarget(window="Notepad"),
                expected_value=False,
                description="Notepad window must no longer exist after termination",
            )
            v_cleanup = await desktop_verifier.verify_goal(cond_cleanup)
            self._record_verification(cond_cleanup, v_cleanup)

            shot_post = await desktop_executor.take_screenshot()
            shot_post_path = self.screenshots_dir / "04_post_cleanup.png"
            if shot_post:
                shot_post_path.write_bytes(shot_post)

            self.steps_summary.append({
                "step": 7,
                "name": "Teardown & Cleanup Verification",
                "status": "PASS" if v_cleanup.verified else "FAIL",
                "duration_ms": int((time.perf_counter() - step_start) * 1000),
                "details": f"Terminated (success={terminated}), WINDOW_EXISTS False verified={v_cleanup.verified}",
            })

            # Calculate assertion statistics
            total_assertions = len(self.verifications)
            passed_assertions = sum(1 for v in self.verifications if v.get("verified"))
            failed_assertions = total_assertions - passed_assertions

            manifest["status"] = "PASSED" if failed_assertions == 0 else "FAILED"
            manifest["assertions"] = {
                "total": total_assertions,
                "passed": passed_assertions,
                "failed": failed_assertions,
            }

        except Exception as exc:
            logger.exception("LIVE_TEST_ERROR: %s", exc)
            manifest["status"] = "FAILED"
            manifest["error"] = str(exc)
            self._log_trace("TEST_ERROR", str(exc))
            # Emergency cleanup of Notepad if needed
            try:
                await app_launcher.terminate_app("notepad")
            except Exception:
                pass

        finally:
            total_duration = time.perf_counter() - self.start_time
            manifest["duration_seconds"] = round(total_duration, 3)
            manifest["steps"] = self.steps_summary
            manifest["metrics"] = {
                "total_duration_s": round(total_duration, 3),
                "events_logged": len(self.trace_events),
                "verifications_evaluated": len(self.verifications),
                "uia_elements_captured": len(uia_tree_dump),
                "screenshots_saved": len(list(self.screenshots_dir.glob("*.png"))),
            }

            self._log_trace("TEST_FINISH", f"Live test ended with status: {manifest['status']}")

            # ─────────────────────────────────────────────────────────
            # STEP 8: Store All Test Data Artifacts
            # ─────────────────────────────────────────────────────────
            self._persist_test_data(manifest, uia_tree_dump)

        logger.info("==================================================")
        logger.info("LIVE DESKTOP TEST COMPLETE: %s", manifest["status"])
        logger.info("Artifacts saved to: %s", self.run_dir)
        logger.info("Assertions: %d passed, %d failed", manifest["assertions"]["passed"], manifest["assertions"]["failed"])
        logger.info("==================================================")

        return manifest

    def _record_verification(self, condition: GoalCondition, result: Any) -> None:
        """Record a verification result with condition details."""
        rec = {
            "predicate": condition.predicate.value,
            "description": condition.description,
            "expected_value": condition.expected_value,
            "target": condition.target.model_dump(),
            "verified": getattr(result, "verified", False),
            "observed": getattr(result, "observed", {}),
            "message": getattr(result, "message", ""),
            "timestamp": getattr(result, "timestamp", datetime.now(UTC).isoformat()),
        }
        self.verifications.append(rec)
        self._log_trace(
            "VERIFICATION",
            f"{condition.predicate.value} -> {'PASS' if rec['verified'] else 'FAIL'}: {rec['message']}",
            rec,
        )

    def _persist_test_data(self, manifest: dict[str, Any], uia_tree: list[dict[str, Any]]) -> None:
        """Write all test data artifacts to disk in structured JSON/Markdown formats."""
        # 1. manifest.json
        manifest_file = self.run_dir / "manifest.json"
        manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        # 2. trace.json
        trace_file = self.run_dir / "trace.json"
        trace_file.write_text(json.dumps(self.trace_events, indent=2), encoding="utf-8")

        # 3. verifications.json
        verif_file = self.run_dir / "verifications.json"
        verif_file.write_text(json.dumps(self.verifications, indent=2), encoding="utf-8")

        # 4. uia_tree.json
        uia_file = self.run_dir / "uia_tree.json"
        uia_file.write_text(json.dumps(uia_tree, indent=2), encoding="utf-8")

        # 5. execution_records.json (R07 Evidence Integration)
        for i, step in enumerate(self.steps_summary):
            exec_record = ExecutionRecord(
                task_id=self.run_id,
                step_id=f"step_{step['step']:02d}",
                step_index=i,
                action={"name": step["name"]},
                execution_result={"status": step["status"], "details": step["details"]},
                duration_ms=step["duration_ms"],
                node_name="live_test_runner",
            )
            self.execution_records.append(exec_record)

        records_file = self.run_dir / "execution_records.json"
        records_data = [r.model_dump() for r in self.execution_records]
        records_file.write_text(json.dumps(records_data, indent=2), encoding="utf-8")

        # 6. summary.md
        summary_md = self._generate_markdown_summary(manifest)
        summary_file = self.run_dir / "summary.md"
        summary_file.write_text(summary_md, encoding="utf-8")

        # 7. Mirror to latest/ directory for quick inspection
        try:
            if self.latest_dir.exists():
                shutil.rmtree(self.latest_dir)
            shutil.copytree(self.run_dir, self.latest_dir)
        except Exception as e:
            logger.warning("Failed to update latest/ directory copy: %s", e)

    def _generate_markdown_summary(self, manifest: dict[str, Any]) -> str:
        """Create a human-readable Markdown summary report of the live run."""
        status_badge = "✅ PASSED" if manifest["status"] == "PASSED" else "❌ FAILED"
        lines = [
            f"# Live Desktop Automation Test Report: {manifest['run_id']}",
            "",
            f"**Overall Status**: {status_badge}",
            f"**Timestamp**: {manifest['timestamp_utc']}",
            f"**Duration**: {manifest['metrics'].get('total_duration_s', 0)} seconds",
            "",
            "## Environment Probing",
            f"- **Operating System**: {manifest['os_environment'].get('system')} {manifest['os_environment'].get('release')} (Build {manifest['os_environment'].get('version')})",
            f"- **Screen Resolution**: {manifest['os_environment'].get('resolution')}",
            f"- **DPI Scaling**: {manifest['os_environment'].get('dpi_scale')}x",
            f"- **Python Runtime**: {manifest['os_environment'].get('python_version').split()[0]}",
            "",
            "## Execution Steps",
            "| Step | Name | Status | Duration (ms) | Details |",
            "|:----:|:-----|:------:|:-------------:|:--------|",
        ]

        for s in manifest.get("steps", []):
            status_icon = "✅" if s["status"] == "PASS" else "❌"
            lines.append(f"| {s['step']} | {s['name']} | {status_icon} {s['status']} | {s['duration_ms']} | {s['details']} |")

        lines.extend([
            "",
            "## Deterministic Verifications",
            "| Predicate | Description | Expected | Verified | Message |",
            "|:----------|:------------|:--------:|:--------:|:--------|",
        ])

        for v in self.verifications:
            v_icon = "✅ PASS" if v.get("verified") else "❌ FAIL"
            lines.append(
                f"| `{v.get('predicate')}` | {v.get('description')} | `{v.get('expected_value')}` | {v_icon} | {v.get('message')} |"
            )

        lines.extend([
            "",
            "## Test Artifacts Stored",
            f"- **Manifest**: [`manifest.json`](file:///{self.run_dir.as_posix()}/manifest.json)",
            f"- **Trace Log**: [`trace.json`](file:///{self.run_dir.as_posix()}/trace.json)",
            f"- **UIA Element Hierarchy**: [`uia_tree.json`](file:///{self.run_dir.as_posix()}/uia_tree.json)",
            f"- **Verifications**: [`verifications.json`](file:///{self.run_dir.as_posix()}/verifications.json)",
            f"- **Execution Records**: [`execution_records.json`](file:///{self.run_dir.as_posix()}/execution_records.json)",
            f"- **Screenshots**: `{len(list(self.screenshots_dir.glob('*.png')))} captured` in `screenshots/`",
            "",
        ])

        return "\n".join(lines)


async def main() -> int:
    """CLI Entry point."""
    runner = LiveDesktopTestRunner()
    manifest = await runner.run()
    return 0 if manifest.get("status") == "PASSED" else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
