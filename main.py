#!/usr/bin/env python3
"""
Agentic-Pilot Primary Application Launcher & Process Orchestrator.

Replaces Windows .bat scripts with a cross-platform, robust Python orchestrator.
Manages application startup, dependency verification, multi-model tiers,
stale port cleanup, health monitoring, and graceful process-tree termination.

Usage:
    python main.py              # Start full application (backend + frontend + ollama)
    python main.py --stop       # Stop all running Pilot background processes
    python main.py --test       # Run automated regression test suite
    python main.py --eval       # Run research evaluation benchmarks & PDF report
    python main.py --backend    # Launch backend API server only
    python main.py --help       # Display usage and CLI options
"""

from __future__ import annotations

import argparse
import atexit
import importlib.util
import json
import logging
import os
from pathlib import Path
import platform
import shutil
import signal
import socket
import subprocess
import sys
import time
from typing import Any
import urllib.error
import urllib.request
import webbrowser

# Project-relative root directory resolution (works from any working directory)
BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR / "backend"
FRONTEND_DIR = BASE_DIR / "frontend"

# Ensure project root is in sys.path
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Color codes for terminal logging
class Colors:
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

    @classmethod
    def strip_colors_if_unsupported(cls) -> None:
        if not sys.stdout.isatty() or platform.system() == "Windows" and os.environ.get("TERM") is None:
            # On Windows without VT support, test if VT can be enabled
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            except Exception:
                cls.CYAN = cls.GREEN = cls.YELLOW = cls.RED = cls.BOLD = cls.DIM = cls.RESET = ""

Colors.strip_colors_if_unsupported()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format=f"{Colors.DIM}%(asctime)s{Colors.RESET} [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pilot.launcher")


class PilotOrchestrator:
    """Manages the full lifecycle of Pilot services."""

    def __init__(
        self,
        backend_port: int = 8765,
        frontend_port: int = 1420,
        ollama_url: str = "http://127.0.0.1:11434",
        text_model: str = "qwen2.5:1.5b",
        vision_model: str = "moondream",
        alt_vision_model: str = "qwen3-vl:2b",
        backend_only: bool = False,
        no_browser: bool = False,
        headless: bool = False,
        with_observatory: bool = False,
    ) -> None:
        self.backend_port = backend_port
        self.frontend_port = frontend_port
        self.ollama_url = ollama_url
        self.text_model = text_model
        self.vision_model = vision_model
        self.alt_vision_model = alt_vision_model
        self.backend_only = backend_only
        self.no_browser = no_browser
        self.headless = headless
        self.with_observatory = with_observatory

        self.child_processes: dict[str, subprocess.Popen[Any]] = {}
        self.active_vision_model = vision_model
        self._is_shutting_down = False

        # Register shutdown handlers
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
        atexit.register(self.shutdown)

    def _handle_signal(self, signum: int, frame: Any) -> None:
        logger.info(f"{Colors.YELLOW}Received shutdown signal. Stopping all Pilot services...{Colors.RESET}")
        self.shutdown()
        sys.exit(0)

    # -------------------------------------------------------------------------
    # Network & Port Utilities
    # -------------------------------------------------------------------------
    def is_port_in_use(self, port: int, host: str = "127.0.0.1") -> bool:
        """Check if a TCP port is currently listening."""
        if not (1 <= port <= 65535):
            return False
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex((host, port)) == 0

    def check_http_health(self, url: str, timeout: float = 2.0) -> bool:
        """Check if an HTTP endpoint returns a successful response."""
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Pilot-Launcher"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                _ = resp.read()
                return 200 <= resp.status < 400
        except Exception:
            return False

    def free_ports(self, ports: list[int] | None = None) -> None:
        """Terminate any processes holding target ports."""
        if ports is None:
            ports = [self.backend_port, self.frontend_port]

        try:
            import psutil
            killed = []
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    if proc.pid > 4:
                        for conn in proc.net_connections(kind="inet"):
                            if conn.laddr and conn.laddr.port in ports:
                                logger.info(
                                    f"Terminating process on port {conn.laddr.port} "
                                    f"(PID: {proc.pid}, Name: {proc.name()})"
                                )
                                proc.terminate()
                                killed.append(proc)
                                break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            if killed:
                gone, alive = psutil.wait_procs(killed, timeout=2.0)
                for p in alive:
                    try:
                        p.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
        except Exception as e:
            logger.debug(f"psutil port cleanup fallback: {e}")

        # Fallback verification: if port still bound, use platform-specific kill
        for port in ports:
            if self.is_port_in_use(port):
                if platform.system() == "Windows":
                    cmd = (
                        f"Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | "
                        "Select-Object -ExpandProperty OwningProcess -Unique | "
                        "ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"
                    )
                    subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True)
                time.sleep(0.5)

    # -------------------------------------------------------------------------
    # Step 1: Environment & Dependency Verification
    # -------------------------------------------------------------------------
    def check_environment(self) -> None:
        """Verify Python environment and install missing dependencies if needed."""
        logger.info(f"{Colors.CYAN}[1/6] Checking Python environment and dependencies...{Colors.RESET}")

        if sys.version_info < (3, 10):
            logger.error(
                f"{Colors.RED}Python 3.10+ required. Running with {sys.version}. "
                f"Please update Python.{Colors.RESET}"
            )
            sys.exit(1)

        logger.info(f"      Python: {sys.version.split()[0]} ({sys.executable})")

        # Check virtualenv presence
        venv_path = BASE_DIR / "venv"
        dot_venv_path = BASE_DIR / ".venv"
        is_venv = (
            hasattr(sys, "real_prefix")
            or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix)
        )
        if is_venv:
            logger.info("      Virtual environment active.")
        elif venv_path.exists() or dot_venv_path.exists():
            logger.info("      Virtual environment detected in project folder.")

        # Check core requirements
        required_modules = [
            "fastapi",
            "uvicorn",
            "playwright",
            "langgraph",
            "aiosqlite",
            "pydantic",
            "httpx",
            "psutil",
        ]
        missing_modules = [mod for mod in required_modules if importlib.util.find_spec(mod) is None]

        if missing_modules:
            logger.warning(
                f"      Missing Python dependencies: {', '.join(missing_modules)}. "
                f"Installing from backend/requirements.txt..."
            )
            req_file = BACKEND_DIR / "requirements.txt"
            if req_file.exists():
                res = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-r", str(req_file)],
                    capture_output=True,
                    text=True,
                )
                if res.returncode != 0:
                    logger.warning(f"      Pip installation reported warnings/errors:\n{res.stderr}")
                else:
                    logger.info(f"{Colors.GREEN}      Python packages installed successfully.{Colors.RESET}")
            else:
                logger.error(f"{Colors.RED}requirements.txt not found at {req_file}{Colors.RESET}")
        else:
            logger.info(f"{Colors.GREEN}      Core Python dependencies verified.{Colors.RESET}")

    # -------------------------------------------------------------------------
    # Step 2: Ollama Daemon
    # -------------------------------------------------------------------------
    def ensure_ollama(self) -> str | None:
        """Check and start the Ollama service if not already responsive."""
        logger.info(f"{Colors.CYAN}[2/6] Checking Ollama service...{Colors.RESET}")

        tags_url = f"{self.ollama_url}/api/tags"
        if self.check_http_health(tags_url):
            logger.info(f"{Colors.GREEN}      Ollama is running at {self.ollama_url}.{Colors.RESET}")
            return shutil.which("ollama")

        # Locate Ollama executable
        ollama_bin = shutil.which("ollama")
        if not ollama_bin and platform.system() == "Windows":
            local_appdata = os.environ.get("LOCALAPPDATA", "")
            prog_files = os.environ.get("ProgramFiles", "")
            candidates = [
                Path(local_appdata) / "Programs" / "Ollama" / "ollama.exe",
                Path(prog_files) / "Ollama" / "ollama.exe",
            ]
            for cand in candidates:
                if cand.exists():
                    ollama_bin = str(cand)
                    break

        if not ollama_bin:
            logger.warning(
                f"{Colors.YELLOW}      Ollama executable not found. "
                f"Install from https://ollama.com. Local LLM/VLM will be unavailable.{Colors.RESET}"
            )
            return None

        logger.info("      Launching Ollama background daemon...")
        proc = subprocess.Popen(
            [ollama_bin, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
        )
        self.child_processes["ollama"] = proc

        # Wait up to 20 seconds for readiness
        ready = False
        for i in range(20):
            time.sleep(1)
            if self.check_http_health(tags_url):
                ready = True
                logger.info(f"{Colors.GREEN}      Ollama daemon is ready ({i + 1}s).{Colors.RESET}")
                break

        if not ready:
            logger.warning("      Ollama did not respond within 20s. Continuing startup...")

        return ollama_bin

    # -------------------------------------------------------------------------
    # Step 3: Multi-Model Availability
    # -------------------------------------------------------------------------
    def verify_models(self, ollama_bin: str | None) -> None:
        """Verify presence of fast text and vision specialist models."""
        logger.info(f"{Colors.CYAN}[3/6] Verifying Multi-Model configuration...{Colors.RESET}")
        if not ollama_bin:
            logger.warning("      Skipping model check (Ollama not found).")
            return

        installed_models: list[str] = []
        try:
            req = urllib.request.Request(f"{self.ollama_url}/api/tags")
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                installed_models = [m.get("name", "") for m in data.get("models", [])]
        except Exception:
            try:
                res = subprocess.run([ollama_bin, "list"], capture_output=True, text=True, timeout=5)
                installed_models = res.stdout.split()
            except Exception:
                pass

        # Text model check
        has_text = any(self.text_model in m for m in installed_models)
        if not has_text:
            logger.info(f"      Pulling fast text model: {self.text_model}...")
            subprocess.run([ollama_bin, "pull", self.text_model], check=False)
        else:
            logger.info(f"{Colors.GREEN}      Fast Text Model ready:   {self.text_model}{Colors.RESET}")

        # Vision model check (prefers qwen3-vl:2b or moondream)
        has_alt = any(self.alt_vision_model in m for m in installed_models)
        has_primary = any(self.vision_model in m for m in installed_models)

        if has_alt:
            self.active_vision_model = self.alt_vision_model
            logger.info(f"{Colors.GREEN}      Vision Specialist ready: {self.active_vision_model}{Colors.RESET}")
        elif has_primary:
            self.active_vision_model = self.vision_model
            logger.info(f"{Colors.GREEN}      Vision Specialist ready: {self.active_vision_model}{Colors.RESET}")
        else:
            logger.info(f"      Pulling vision model: {self.vision_model}...")
            subprocess.run([ollama_bin, "pull", self.vision_model], check=False)
            self.active_vision_model = self.vision_model
            logger.info(f"{Colors.GREEN}      Vision Specialist ready: {self.active_vision_model}{Colors.RESET}")

    # -------------------------------------------------------------------------
    # Step 4: Playwright Browser Engine
    # -------------------------------------------------------------------------
    def verify_playwright(self) -> None:
        """Verify Playwright Chromium browser binary can launch."""
        logger.info(f"{Colors.CYAN}[4/6] Verifying Playwright browser engine...{Colors.RESET}")
        check_code = (
            "from playwright.sync_api import sync_playwright; "
            "p = sync_playwright().start(); "
            "b = p.chromium.launch(headless=True); "
            "b.close(); "
            "p.stop(); "
            "print('OK')"
        )
        res = subprocess.run([sys.executable, "-c", check_code], capture_output=True, text=True)
        if res.returncode != 0:
            logger.info("      Playwright Chromium binary not found. Installing Chromium...")
            install_res = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                capture_output=True,
                text=True,
            )
            if install_res.returncode != 0:
                logger.warning(f"      Playwright install warning: {install_res.stderr}")
            else:
                logger.info(f"{Colors.GREEN}      Playwright Chromium installed successfully.{Colors.RESET}")
        else:
            logger.info(f"{Colors.GREEN}      Playwright Chromium verified and ready.{Colors.RESET}")

    # -------------------------------------------------------------------------
    # Step 5: Launch Backend Server
    # -------------------------------------------------------------------------
    def start_backend(self) -> None:
        """Launch the FastAPI backend server and wait for health check."""
        logger.info(f"{Colors.CYAN}[5/6] Launching Pilot Backend (FastAPI + LangGraph)...{Colors.RESET}")

        env = os.environ.copy()
        env["PYTHONPATH"] = str(BASE_DIR)
        env["PILOT_SERVER_PORT"] = str(self.backend_port)
        env["PILOT_OLLAMA_BASE_URL"] = self.ollama_url
        env["PILOT_OLLAMA_MODEL"] = self.text_model
        env["PILOT_OLLAMA_VISION_MODEL"] = self.active_vision_model
        if self.headless:
            env["PILOT_HEADLESS_BROWSER"] = "true"

        backend_script = BACKEND_DIR / "main.py"
        proc = subprocess.Popen(
            [sys.executable, str(backend_script)],
            cwd=str(BASE_DIR),
            env=env,
        )
        self.child_processes["backend"] = proc

        # Health polling
        health_url = f"http://127.0.0.1:{self.backend_port}/health"
        backend_ready = False
        for i in range(20):
            time.sleep(1)
            if self.check_http_health(health_url):
                backend_ready = True
                logger.info(f"{Colors.GREEN}      Backend API is live at http://127.0.0.1:{self.backend_port} ({i + 1}s).{Colors.RESET}")
                break

            if proc.poll() is not None:
                logger.error(f"{Colors.RED}Backend process terminated prematurely with code {proc.returncode}.{Colors.RESET}")
                break

        if not backend_ready:
            logger.warning("      Backend did not respond to /health within 20s. Check logs.")

    # -------------------------------------------------------------------------
    # Step 6: Launch Frontend Dev Server
    # -------------------------------------------------------------------------
    def start_frontend(self) -> None:
        """Verify Node/npm, install modules if missing, and start dev server."""
        if self.backend_only:
            logger.info("      Skipping frontend launch (--backend-only active).")
            return

        logger.info(f"{Colors.CYAN}[6/6] Launching Pilot Frontend (Vite + React)...{Colors.RESET}")
        npm_bin = shutil.which("npm")
        if not npm_bin:
            logger.error(
                f"{Colors.RED}npm not found in PATH! Install Node.js 20+ from https://nodejs.org "
                f"to run the web frontend.{Colors.RESET}"
            )
            return

        # Check dependencies
        node_modules = FRONTEND_DIR / "node_modules"
        if not node_modules.exists():
            logger.info("      Installing frontend dependencies (npm install)...")
            subprocess.run([npm_bin, "install"], cwd=str(FRONTEND_DIR), check=True)

        env = os.environ.copy()
        proc = subprocess.Popen(
            [npm_bin, "run", "dev"],
            cwd=str(FRONTEND_DIR),
            env=env,
        )
        self.child_processes["frontend"] = proc

        frontend_url = f"http://127.0.0.1:{self.frontend_port}"
        frontend_ready = False
        for i in range(15):
            time.sleep(1)
            if self.check_http_health(frontend_url):
                frontend_ready = True
                logger.info(f"{Colors.GREEN}      Frontend UI is live at {frontend_url} ({i + 1}s).{Colors.RESET}")
                break

            if proc.poll() is not None:
                logger.error(f"{Colors.RED}Frontend dev server terminated prematurely with code {proc.returncode}.{Colors.RESET}")
                break

        # Open web browser
        if not self.no_browser and frontend_ready:
            logger.info(f"      Opening Pilot Workbench in browser: {frontend_url}")
            webbrowser.open(frontend_url)

    # -------------------------------------------------------------------------
    # Optional Step: Launch Observatory
    # -------------------------------------------------------------------------
    def start_observatory(self) -> None:
        """Start Observatory backend (port 8766) and frontend (port 3001)."""
        if not self.with_observatory:
            return

        logger.info(f"{Colors.CYAN}Launching Pilot Agent Observatory (Backend :8766, Frontend :3001)...{Colors.RESET}")
        obs_dir = BASE_DIR / "observatory"
        obs_frontend_dir = obs_dir / "frontend"

        # Backend :8766
        obs_backend_cmd = [sys.executable, "-m", "observatory.backend.main"]
        obs_backend_proc = subprocess.Popen(obs_backend_cmd, cwd=str(BASE_DIR), env=os.environ.copy())
        self.child_processes["observatory_backend"] = obs_backend_proc

        # Frontend :3001
        npm_bin = shutil.which("npm")
        if npm_bin and obs_frontend_dir.exists():
            obs_front_proc = subprocess.Popen([npm_bin, "run", "dev"], cwd=str(obs_frontend_dir), env=os.environ.copy())
            self.child_processes["observatory_frontend"] = obs_front_proc

        logger.info(f"{Colors.GREEN}      Observatory is live at http://127.0.0.1:3001{Colors.RESET}")
        if not self.no_browser:
            time.sleep(1)
            webbrowser.open("http://127.0.0.1:3001")

    # -------------------------------------------------------------------------
    # Interactive Management Loop
    # -------------------------------------------------------------------------
    def run_interactive_manager(self) -> None:
        """Display live service dashboard and interactive options."""
        print()
        print(f"{Colors.CYAN}{'=' * 60}{Colors.RESET}")
        print(f"{Colors.BOLD}  PILOT SERVICES OPERATIONAL!{Colors.RESET}")
        print(f"{Colors.CYAN}{'=' * 60}{Colors.RESET}")
        print(f"  Frontend Web UI : http://127.0.0.1:{self.frontend_port}")
        print(f"  Backend REST API: http://127.0.0.1:{self.backend_port}")
        if self.with_observatory:
            print("  Observatory UI  : http://127.0.0.1:3001")
            print("  Observatory API : http://127.0.0.1:8766")
        print(f"  Ollama Service  : {self.ollama_url}")
        print(f"  Fast Text Model : {self.text_model}")
        print(f"  Vision Model    : {self.active_vision_model}")
        print("  Browser Engine  : Playwright Chromium (Stealth)")
        print(f"{Colors.CYAN}{'=' * 60}{Colors.RESET}")
        print()
        print("  Controls:")
        print("    [B] Open / Re-open Web UI in browser")
        print("    [T] Run Automated Regression Test Suite")
        print("    [S] Check Service Health Status")
        print("    [R] Restart Services")
        print("    [Q] Cleanly Stop All Services and Exit (or Ctrl+C)")
        print()

        warned_exits: set[str] = set()
        try:
            while not self._is_shutting_down:
                # Check process liveness
                critical_died = False
                for name, p in list(self.child_processes.items()):
                    if p.poll() is not None:
                        if name not in warned_exits:
                            logger.warning(f"Process '{name}' exited with return code {p.returncode}")
                            warned_exits.add(name)
                        if name in ("backend", "frontend"):
                            critical_died = True

                # In non-interactive mode, exit cleanly if a critical service dies
                if not sys.stdin.isatty():
                    if critical_died:
                        logger.info("Critical child process exited. Stopping supervisor.")
                        break
                    time.sleep(2)
                    continue

                # Prompt option if running in interactive terminal
                try:
                    choice = input("Command [B, T, S, R, Q] > ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    break

                if choice == "b":
                    webbrowser.open(f"http://127.0.0.1:{self.frontend_port}")
                elif choice == "t":
                    self.run_tests()
                elif choice == "s":
                    self.check_status()
                elif choice == "r":
                    logger.info("Restarting Pilot services...")
                    self.shutdown(keep_ollama=True)
                    time.sleep(1)
                    self.free_ports()
                    self.start_backend()
                    self.start_frontend()
                    warned_exits.clear()
                elif choice in ("q", "quit", "exit"):
                    break
        except KeyboardInterrupt:
            pass
        finally:
            self.shutdown()

    def check_status(self) -> None:
        """Inspect and print status of each service."""
        print(f"\n{Colors.CYAN}--- System Health Status ---{Colors.RESET}")
        backend_ok = self.check_http_health(f"http://127.0.0.1:{self.backend_port}/health")
        print(f"  Backend API:   {'[OK] Healthy' if backend_ok else '[FAIL] Offline'}")

        frontend_ok = self.check_http_health(f"http://127.0.0.1:{self.frontend_port}")
        print(f"  Frontend UI:   {'[OK] Live' if frontend_ok else '[FAIL] Offline'}")

        ollama_ok = self.check_http_health(f"{self.ollama_url}/api/tags")
        print(f"  Ollama Daemon: {'[OK] Active' if ollama_ok else '[FAIL] Offline'}\n")

    def run_tests(self) -> int:
        """Execute automated regression test suite."""
        print(f"\n{Colors.CYAN}============================================================{Colors.RESET}")
        print(f"{Colors.BOLD}  Running Automated Regression Test Suite...{Colors.RESET}")
        print(f"{Colors.CYAN}============================================================{Colors.RESET}\n")
        test_files = [
            "tests/test_navigation_transition_and_typing.py",
            "tests/test_browser_agent_pipeline.py",
            "tests/test_captcha_handling.py",
        ]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(BASE_DIR)
        res = subprocess.run([sys.executable, "-m", "pytest", *test_files, "-v"], cwd=str(BASE_DIR), env=env)
        return res.returncode

    def run_eval(self) -> int:
        """Execute research evaluation benchmarks."""
        print(f"\n{Colors.CYAN}============================================================{Colors.RESET}")
        print(f"{Colors.BOLD}  Running Research Evaluation Benchmarks...{Colors.RESET}")
        print(f"{Colors.CYAN}============================================================{Colors.RESET}\n")
        eval_scripts = [
            "scratch/phase3_startup_eval.py",
            "scratch/phase4_5_6_eval.py",
            "scratch/phase7_8_9_rag_memory_eval.py",
            "scratch/phase10_checkpoint_eval.py",
            "scratch/phase11_playwright_eval.py",
            "scratch/phase12_13_14_eval.py",
            "scratch/phase16_to_21_eval.py",
            "scratch/generate_pdf_report.py",
        ]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(BASE_DIR)
        for script in eval_scripts:
            path = BASE_DIR / script
            if path.exists():
                logger.info(f"Running {script}...")
                res = subprocess.run([sys.executable, str(path)], cwd=str(BASE_DIR), env=env)
                if res.returncode != 0:
                    logger.error(f"Evaluation script {script} failed with code {res.returncode}")
                    return res.returncode
        return 0

    # -------------------------------------------------------------------------
    # Shutdown & Process Tree Termination
    # -------------------------------------------------------------------------
    def shutdown(self, keep_ollama: bool = True) -> None:
        """Cleanly terminate child processes and ensure ports are freed."""
        if self._is_shutting_down:
            return
        self._is_shutting_down = True
        logger.info(f"{Colors.YELLOW}Stopping Pilot child processes...{Colors.RESET}")

        try:
            import psutil
            for name, proc in list(self.child_processes.items()):
                if name == "ollama" and keep_ollama:
                    continue
                if proc and proc.poll() is None:
                    try:
                        parent = psutil.Process(proc.pid)
                        children = parent.children(recursive=True)
                        for child in children:
                            try:
                                child.terminate()
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                pass
                        parent.terminate()
                        gone, alive = psutil.wait_procs(children + [parent], timeout=2.0)
                        for p in alive:
                            try:
                                p.kill()
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                pass
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
        except Exception as e:
            logger.debug(f"Process tree termination fallback: {e}")
            for name, proc in list(self.child_processes.items()):
                if name == "ollama" and keep_ollama:
                    continue
                if proc and proc.poll() is None:
                    proc.terminate()

        # Clean ports
        self.free_ports([self.backend_port, self.frontend_port])
        self.child_processes.clear()
        self._is_shutting_down = False
        logger.info(f"{Colors.GREEN}All Pilot services stopped cleanly.{Colors.RESET}")

    # -------------------------------------------------------------------------
    # Main Execution Flow
    # -------------------------------------------------------------------------
    def start(self) -> None:
        """Execute the full startup lifecycle."""
        print()
        print(f"{Colors.CYAN}{'=' * 60}{Colors.RESET}")
        print(f"{Colors.BOLD}  Agentic-Pilot  -  Unified Python Application Orchestrator{Colors.RESET}")
        print("  Evidence-Driven Browser Automation & Knowledge Framework")
        print(f"{Colors.CYAN}{'=' * 60}{Colors.RESET}\n")

        # Step 0: Free target ports
        logger.info(f"{Colors.CYAN}[0/6] Clearing stale processes on ports {self.backend_port}, {self.frontend_port}...{Colors.RESET}")
        self.free_ports()
        logger.info(f"{Colors.GREEN}      Target ports are clear.{Colors.RESET}")

        # Step 1: Environment & Dependencies
        self.check_environment()

        # Step 2: Ollama daemon
        ollama_bin = self.ensure_ollama()

        # Step 3: Multi-model availability
        self.verify_models(ollama_bin)

        # Step 4: Playwright engine
        self.verify_playwright()

        # Step 5: Backend
        self.start_backend()

        # Step 6: Frontend
        self.start_frontend()

        # Step 7: Optional Observatory
        self.start_observatory()

        # Interactive manager loop
        self.run_interactive_manager()


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Agentic-Pilot Unified Python Application Launcher & Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--stop", action="store_true", help="Stop all running Pilot background processes and free ports")
    parser.add_argument("--test", action="store_true", help="Run automated regression test suite")
    parser.add_argument("--eval", action="store_true", help="Run research evaluation benchmarks & PDF report")
    parser.add_argument("--backend-only", action="store_true", help="Launch only the backend API server")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically launch web browser")
    parser.add_argument("--headless", action="store_true", help="Run browser automation in headless mode")
    parser.add_argument("--port", type=int, default=8765, help="Backend port (default: 8765)")
    parser.add_argument("--frontend-port", type=int, default=1420, help="Frontend port (default: 1420)")
    parser.add_argument("--ollama-url", type=str, default="http://127.0.0.1:11434", help="Ollama base URL")
    parser.add_argument("--text-model", type=str, default="qwen2.5:1.5b", help="Fast text/planner model")
    parser.add_argument("--vision-model", type=str, default="moondream", help="Vision specialist model")
    parser.add_argument("--observatory", action="store_true", help="Launch Pilot Agent Observatory on http://127.0.0.1:3001")
    return parser.parse_args()


def main() -> int:
    """Main application entry point."""
    args = parse_args()

    orchestrator = PilotOrchestrator(
        backend_port=args.port,
        frontend_port=args.frontend_port,
        ollama_url=args.ollama_url,
        text_model=args.text_model,
        vision_model=args.vision_model,
        backend_only=args.backend_only,
        no_browser=args.no_browser,
        headless=args.headless,
        with_observatory=args.observatory,
    )

    if args.stop:
        logger.info("Stopping all Pilot background processes...")
        orchestrator.free_ports()
        logger.info(f"{Colors.GREEN}Ports {args.port} and {args.frontend_port} cleared successfully.{Colors.RESET}")
        return 0

    if args.test:
        return orchestrator.run_tests()

    if args.eval:
        return orchestrator.run_eval()

    try:
        orchestrator.start()
        return 0
    except Exception as e:
        logger.error(f"{Colors.RED}Startup error: {e}{Colors.RESET}", exc_info=True)
        orchestrator.shutdown()
        return 1


if __name__ == "__main__":
    sys.exit(main())
