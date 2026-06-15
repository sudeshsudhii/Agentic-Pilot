#!/usr/bin/env bash
set -euo pipefail

echo "Setting up Pilot..."

find_python() {
  for candidate in python3.12 python3.11 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      "$candidate" - <<'PY' >/dev/null 2>&1 && { echo "$candidate"; return 0; }
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
    fi
  done

  return 1
}

PYTHON_BIN="$(find_python || true)"
if [[ -z "$PYTHON_BIN" ]]; then
  echo "Python 3.11+ is required. Install it, then rerun ./setup.sh."
  exit 1
fi

echo "Using Python: $("$PYTHON_BIN" --version)"

if [[ ! -d venv ]]; then
  "$PYTHON_BIN" -m venv venv
fi

if [[ -f venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
elif [[ -f venv/Scripts/activate ]]; then
  # shellcheck disable=SC1091
  source venv/Scripts/activate
else
  echo "Could not find the virtual environment activation script."
  exit 1
fi

python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
python -m playwright install chromium

if command -v npm >/dev/null 2>&1; then
  (cd frontend && npm install)
else
  echo "npm is not installed. Install Node.js 20+ to run the React/Tauri frontend."
fi

if command -v cargo >/dev/null 2>&1; then
  if ! command -v cargo-tauri >/dev/null 2>&1; then
    echo "Tauri CLI not found. Install with: cargo install tauri-cli"
  fi
else
  echo "Rust/Cargo is not installed. Install Rust before running the desktop shell."
fi

if command -v ollama >/dev/null 2>&1; then
  echo "Ollama found: $(ollama --version)"
else
  echo "Ollama is not installed."
  echo "Install it from https://ollama.ai, then run: ollama pull qwen2.5:7b"
fi

mkdir -p "$HOME/.pilot/logs"

echo "Setup complete. Run: python backend/main.py"
echo "Frontend dev server: cd frontend && npm run dev"
echo "Desktop dev mode: cd frontend && npm run tauri dev"
