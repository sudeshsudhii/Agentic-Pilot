# Changelog

## [1.0.0] - Production Research Edition

### Added
- **Hard Execution Verification**: Playwright actions now explicitly verify URL and DOM mutation state changes.
- **Evidence Framework**: Added `EvidenceManager` to generate `trace.json`, `before.png`, `after.png`, and `dom_snapshot.json` in `~/.pilot/evidence/`.
- **Granular Event Streaming**: Task Runner now streams exact LangGraph edge transitions natively to SQLite.
- **Certification Scripts**: Created `scripts/certify.py` for automated E2E task execution proofs.
- **Memory & Vision Validations**: Created automated scripts to validate vector memory storage and Vision fallback pathways.
- **Benchmark Suite**: Added `benchmarks/run.py` to evaluate latency, success rates, and coverage metrics.
- **E2E Tests**: Added `tests/e2e/test_runner.py` for LangGraph and Approval flow coverage.

### Removed
- **Heuristic Parsing Fallback**: Completely deleted `heuristic_parse_intent`. Tasks will now strictly fail if the LLM cannot parse intent, preventing mock simulated completions.
- **Simulated Execution**: Removed hardcoded navigation and search fallback stubs from the runner.

### Fixed
- Fixed unhandled parsing exceptions crashing the graph by routing `failed` states to `error_recovery`.
