# Contributing to Agentic Pilot

We welcome contributions to Agentic Pilot! Whether you are fixing bugs, proposing new features, or improving documentation, your help is appreciated.

## Getting Started

1. Fork the repository
2. Install Python 3.11+, Node.js 20+, and Rust/Cargo.
3. Install backend dependencies via `pip install -r backend/requirements.txt`.
4. Install frontend dependencies via `npm install` inside `frontend/`.
5. Run the local backend via `python backend/main.py`.
6. Run the local frontend via `npm run dev` in `frontend/`.

## Architecture Overview

Agentic Pilot uses a modular architecture:
- `backend/`: FastAPI + LangGraph state machine agent.
- `frontend/`: React + Vite web UI.
- `src-tauri/`: Tauri desktop environment wrapper.

## Pull Request Guidelines

- Ensure your code passes linting (`ruff check backend/`).
- If you're adding a feature, please include tests.
- Reference related issues in your PR description.
- Keep PRs focused on a single change or feature.

Thank you for contributing!
