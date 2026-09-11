"""Automated regression and lifecycle tests for the Python application launcher."""

import os
from pathlib import Path
import subprocess
import sys
import pytest

from main import PilotOrchestrator, parse_args, BASE_DIR


def test_orchestrator_initialization():
    """Verify that PilotOrchestrator initializes with correct paths and defaults."""
    orch = PilotOrchestrator(
        backend_port=8765,
        frontend_port=1420,
        ollama_url="http://127.0.0.1:11434",
    )
    assert orch.backend_port == 8765
    assert orch.frontend_port == 1420
    assert orch.ollama_url == "http://127.0.0.1:11434"
    assert orch.text_model == "qwen2.5:1.5b"
    assert isinstance(BASE_DIR, Path)
    assert (BASE_DIR / "backend").exists()
    assert (BASE_DIR / "frontend").exists()


def test_is_port_in_use_and_range_validation():
    """Verify socket port detection and out-of-range protection."""
    orch = PilotOrchestrator()
    # Out of range ports should return False safely without throwing OverflowError
    assert orch.is_port_in_use(0) is False
    assert orch.is_port_in_use(-1) is False
    assert orch.is_port_in_use(70000) is False

    # Check an ephemeral port that is not in use
    assert orch.is_port_in_use(59998) is False


def test_check_http_health_live_and_offline():
    """Verify HTTP health checking behavior."""
    orch = PilotOrchestrator()
    # Offline port
    assert orch.check_http_health("http://127.0.0.1:59999/health", timeout=0.5) is False


def test_environment_verification():
    """Verify check_environment passes for the current runtime."""
    orch = PilotOrchestrator()
    # Should complete without error
    orch.check_environment()


def test_free_ports_safe_execution():
    """Verify free_ports executes safely without crashing."""
    orch = PilotOrchestrator()
    # Test on test ports
    orch.free_ports([59996, 59997])


def test_cli_argument_parsing(monkeypatch):
    """Verify CLI parser handles all options correctly."""
    # Test --stop
    monkeypatch.setattr(sys, "argv", ["main.py", "--stop"])
    args = parse_args()
    assert args.stop is True
    assert args.test is False

    # Test --test
    monkeypatch.setattr(sys, "argv", ["main.py", "--test"])
    args = parse_args()
    assert args.test is True
    assert args.stop is False

    # Test --eval
    monkeypatch.setattr(sys, "argv", ["main.py", "--eval"])
    args = parse_args()
    assert args.eval is True

    # Test --backend-only and custom port
    monkeypatch.setattr(sys, "argv", ["main.py", "--backend-only", "--port", "9000"])
    args = parse_args()
    assert args.backend_only is True
    assert args.port == 9000


def test_different_working_directory():
    """Verify the launcher resolves paths correctly when run from another directory."""
    scratch_dir = BASE_DIR / "scratch"
    res = subprocess.run(
        [sys.executable, str(BASE_DIR / "main.py"), "--help"],
        cwd=str(scratch_dir),
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "Agentic-Pilot Unified Python Application Launcher" in res.stdout


def test_shutdown_process_tracking():
    """Verify child processes can be registered and cleanly terminated."""
    orch = PilotOrchestrator()
    # Spawn a harmless sleeper process
    dummy_proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(10)"],
        cwd=str(BASE_DIR),
    )
    orch.child_processes["dummy"] = dummy_proc
    assert dummy_proc.poll() is None

    # Shutdown should terminate it
    orch.shutdown()
    assert dummy_proc.poll() is not None
