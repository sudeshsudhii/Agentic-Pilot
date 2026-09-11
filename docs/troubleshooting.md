# Agentic Pilot — Troubleshooting Guide

Common issues, diagnostic procedures, and resolutions for running Agentic Pilot locally.

---

## 1. Local Model & Ollama Issues

### Issue: `OLLAMA_CALL failed: Connection refused`
- **Cause**: The Ollama daemon is not running or listening on port `11434`.
- **Resolution**:
  ```bash
  # Check if Ollama is running
  curl http://127.0.0.1:11434/api/tags
  
  # Start Ollama service
  ollama serve
  ```

### Issue: `Model not found: qwen2.5:1.5b`
- **Cause**: The required local model candidate has not been pulled.
- **Resolution**:
  ```bash
  ollama pull qwen2.5:1.5b
  ollama pull moondream
  ```

---

## 2. Browser Automation & Playwright Issues

### Issue: `Executable doesn't exist at ...`
- **Cause**: Playwright Chromium binary is not installed in the current environment.
- **Resolution**:
  ```bash
  playwright install chromium
  ```

### Issue: Port Collisions (`Address already in use: 8765 / 8766 / 1420 / 3001`)
- **Cause**: Previous background instances of Pilot or Observatory are still holding ports.
- **Resolution**:
  ```bash
  # Gracefully stop all Pilot background services
  python main.py --stop
  
  # On Windows, stop.bat forwards directly to:
  stop.bat
  ```

---

## 3. CAPTCHA & Bot Verification Handling

### Observed State: `Task Status: BLOCKED`
- **Cause**: The visited site (e.g. Google Search) presented an automated bot challenge, Cloudflare turnstile, or `/sorry/` challenge page.
- **Framework Behavior**:
  - Agentic Pilot **does not** attempt to bypass or solve CAPTCHAs automatically.
  - The task transitions to `BLOCKED`.
  - A proof screenshot is captured and saved.
  - The browser session remains open on the challenge page.
- **Resolution Options**:
  1. **Manual Solve**: Solve the challenge directly in the visible browser window, then click **Resume** in the Pilot UI.
  2. **Alternative Search Fallback**: Switch the query provider to DuckDuckGo via the UI or API fallback option.

---

## 4. Verification Failures & Recovery Loops

### Issue: `Task verification failed: Text mismatch`
- **Cause**: The text typed into an input field does not match the prompt's required string, or JavaScript cleared the field.
- **Resolution**:
  - Inspect the **Visual Proof Carousel** in the Agent Observatory (`http://127.0.0.1:3001`).
  - Compare the `Expected` vs `Observed` state cards to identify whether the target element selector changed.
  - Increase retry budget in `.env` (`PILOT_MAX_RETRY_COUNT=5`) if the target website exhibits high latency.
