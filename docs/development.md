# Agentic Pilot — Developer Guide

This document covers development workflows, code standards, test execution, and extension points for Agentic Pilot.

---

## 1. Development Prerequisites

- **Python**: 3.11 or newer (Python 3.14 compatible)
- **Node.js**: 20 LTS or newer
- **Playwright Chromium**: Managed via `playwright install chromium`
- **Ollama**: Local Ollama runtime running with required models pulled

---

## 2. Environment Setup

```bash
# 1. Clone repository
git clone https://github.com/sudeshsudhii/Agentic-pilot-local.git
cd Agentic-pilot-local

# 2. Set up Python virtual environment
python -m venv .venv
source .venv/bin/activate  # Or `.venv\Scripts\activate` on Windows

# 3. Install backend dependencies
pip install -r backend/requirements.txt
playwright install chromium

# 4. Install frontend dependencies
cd frontend && npm install && cd ..
cd observatory/frontend && npm install && cd ..
```

---

## 3. Running Services for Development

You can run individual subsystems or launch all services concurrently using `main.py`:

```bash
# Launch entire ecosystem (Backend :8765, Pilot UI :1420, Observatory Backend :8766, Observatory UI :3001)
python main.py

# Launch only backend API server
python main.py --backend-only

# Launch without auto-opening web browser
python main.py --no-browser

# Stop all background services
python main.py --stop
```

---

## 4. Test Suite Execution

Agentic Pilot includes a 100+ automated test suite across unit, integration, and end-to-end components.

```bash
# Run all automated tests
python -m pytest

# Run specific test modules
python -m pytest tests/test_case_study_enhancements.py -v
python -m pytest tests/test_captcha_handling.py -v
python -m pytest tests/test_navigation_transition_and_typing.py -v
python -m pytest observatory/tests/test_observatory.py -v

# Run with test launcher flag
python main.py --test
```

---

## 5. Frontend Production Builds

Both the user application and the developer observatory use Vite and TypeScript:

```bash
# Build Pilot user interface
cd frontend
npm run build

# Build Agent Observatory interface
cd ../observatory/frontend
npm run build
```

---

## 6. Extending the Agent

### Adding a Custom Plugin
Plugins reside under `plugins/<plugin_name>/` and implement the `BasePlugin` interface.
Each plugin provides:
- `manifest.json`: Defines tools, descriptions, and required permissions.
- `plugin.py`: Implements executable methods called by the agent runner.

### Adding an Action Type
1. Define the action schema in `backend/llm/parser.py`.
2. Add execution logic to `PlaywrightExecutor` in `backend/browser/executor.py`.
3. Add verification checks in `backend/verification/manager.py`.
