"""Recovery engine for managing execution failures with strategy escalation."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from backend.agent.state import AgentState

logger = logging.getLogger("pilot.recovery")


class RecoveryRecord(BaseModel):
    """Structured record of a recovery attempt (R10).

    Captures failure classification, diagnosis, strategy used,
    and outcome for research measurement.
    """

    failure_type: str
    diagnosis: str
    strategy: str
    retry_count: int
    max_retries: int
    outcome: str  # "retry", "escalated", "exhausted"
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


# Failure classification hierarchy
# NOTE: Desktop-specific types MUST come before generic browser types
# because classification uses first-match and "not found" in element_not_found
# would shadow "Window not found" in desktop_window_not_found.
FAILURE_TYPES = {
    "captcha": ["captcha", "recaptcha", "sorry/index", "unusual traffic", "automated queries", "bot verification", "i'm not a robot"],
    "transient": ["timeout", "Timeout", "net::ERR_", "CONNECTION"],
    # Desktop-specific failure types (checked before generic browser types)
    "desktop_element_not_found": ["Grounding failed", "All grounding levels exhausted", "Element not in observation"],
    "desktop_window_not_found": ["Window not found", "Unknown application"],
    "desktop_security_boundary": ["Security boundary", "UAC elevation", "consent.exe"],
    "desktop_uia_failure": ["uiautomation", "COM error"],
    "desktop_grounding_failed": ["grounding_level\":\"failed"],
    # Generic browser failure types
    "element_not_found": ["Element has no usable", "Unsupported action", "missing element", "element not found"],
    "verification_failed": ["Verification failed", "Input verification failed"],
    "navigation_failed": ["Navigation failed", "DNS", "chrome-error"],
    "vision_needed": ["need_help", "Cannot find element"],
    "llm_failure": ["LLM failure", "Structured LLM response", "not valid JSON"],
}


# Strategy escalation order
STRATEGY_LEVELS = [
    "retry",                # Same action, same selector
    "alternative_selector", # Same action, try different selector approach
    "vision_fallback",      # Use VLM to find element visually
    "replan",               # Ask LLM to choose a completely different action
]

# Desktop-specific strategy escalation
DESKTOP_STRATEGY_LEVELS = [
    "retry",                    # Re-observe and retry same action
    "reobserve",                # Fresh observation and replan
    "keyboard_navigation",      # Fall back to Tab/Enter/shortcuts
    "vision_grounding",         # Use VLM to locate element visually
    "replan",                   # Full replanning with different approach
]


class RecoveryEngine:
    """Manages strategy escalation for failed browser tasks.

    Implements the recovery pipeline:
    Failure → Classification → Diagnosis → Strategy → Retry → Verify
    with bounded retries per strategy level (R10).
    """

    def __init__(self, max_retries_per_strategy: int = 2, max_total_retries: int = 6):
        self.max_retries_per_strategy = max_retries_per_strategy
        self.max_total_retries = max_total_retries
        self._recovery_history: dict[str, list[RecoveryRecord]] = {}

    def classify_failure(self, error: str) -> str:
        """Classify a failure error message into a failure type."""
        error_lower = error.lower() if error else ""
        for failure_type, patterns in FAILURE_TYPES.items():
            for pattern in patterns:
                if pattern.lower() in error_lower:
                    return failure_type
        return "unknown"

    def diagnose(self, failure_type: str, error: str | None, state: AgentState) -> str:
        """Produce a human-readable diagnosis of the failure."""
        action = state.get("planned_action")
        action_type = action.action_type if action else "unknown"
        safe_error = str(error or "Unknown failure")

        diagnoses = {
            "captcha": "Google requires human verification (CAPTCHA / bot verification detected).",
            "transient": f"Transient network/timeout error during {action_type}. May succeed on retry.",
            "element_not_found": f"Target element could not be located for {action_type}. Selector may be stale.",
            "verification_failed": f"Action {action_type} executed but verification of result failed.",
            "navigation_failed": f"Navigation to target site failed. DNS or connectivity issue.",
            "vision_needed": f"DOM-based element finding failed for {action_type}. Vision model may help.",
            "llm_failure": f"LLM could not produce valid structured response for {action_type}.",
            "unknown": f"Unclassified failure during {action_type}: {safe_error[:100]}",
        }
        return diagnoses.get(failure_type, diagnoses["unknown"])

    def select_strategy(self, failure_type: str, retry_count: int) -> str:
        """Select the appropriate recovery strategy based on failure type and retry count."""
        if failure_type == "captcha":
            return "blocked"

        if retry_count >= self.max_total_retries:
            return "exhausted"

        # Determine which strategy level based on retries
        strategy_index = min(retry_count // self.max_retries_per_strategy, len(STRATEGY_LEVELS) - 1)

        # Some failure types map directly to specific strategies
        if failure_type == "vision_needed":
            return "vision_fallback"
        if failure_type == "verification_failed" and retry_count >= self.max_retries_per_strategy:
            return "replan"
        if failure_type == "navigation_failed":
            return "retry" if retry_count < 2 else "replan"

        # Desktop-specific strategies
        if failure_type == "desktop_security_boundary":
            return "blocked"
        if failure_type == "desktop_element_not_found":
            if retry_count < 2:
                return "reobserve"
            return "keyboard_navigation" if retry_count < 4 else "vision_grounding"
        if failure_type == "desktop_window_not_found":
            return "retry" if retry_count < 2 else "replan"
        if failure_type == "desktop_grounding_failed":
            return "vision_grounding" if retry_count < 3 else "replan"
        if failure_type == "desktop_uia_failure":
            return "reobserve" if retry_count < 2 else "replan"

        return STRATEGY_LEVELS[strategy_index]

    async def handle_failure(self, state: AgentState) -> dict[str, Any]:
        """Determine next recovery step after a failure.

        Returns state updates including strategy signal for the graph router.
        """
        from backend.config import get_config
        config = get_config()

        retry_count = state.get("retry_count", 0)
        error = state.get("error") or "Execution failure"
        task_id = state.get("task_id", "unknown")

        # If recovery is disabled, fail immediately
        if not config.enable_recovery:
            logger.info("RECOVERY disabled — failing task_id=%s", task_id)
            return {"status": "failed", "error": error}

        # Classify and diagnose
        failure_type = self.classify_failure(error)
        diagnosis = self.diagnose(failure_type, error, state)

        # Check bounds
        if retry_count >= self.max_total_retries:
            record = RecoveryRecord(
                failure_type=failure_type,
                diagnosis=diagnosis,
                strategy="exhausted",
                retry_count=retry_count,
                max_retries=self.max_total_retries,
                outcome="exhausted",
            )
            self._save_record(task_id, record)
            logger.error(
                "RECOVERY EXHAUSTED task_id=%s failure_type=%s retries=%d/%d",
                task_id, failure_type, retry_count, self.max_total_retries,
            )
            return {
                "status": "failed",
                "error": f"Recovery exhausted ({retry_count} attempts). Last: {diagnosis}",
                "recovery_record": record.model_dump(),
            }

        # Select strategy
        strategy = self.select_strategy(failure_type, retry_count)

        if strategy == "blocked" or failure_type == "captcha":
            record = RecoveryRecord(
                failure_type="captcha",
                diagnosis=diagnosis,
                strategy="blocked",
                retry_count=retry_count,
                max_retries=self.max_total_retries,
                outcome="blocked",
            )
            self._save_record(task_id, record)
            logger.warning("RECOVERY BLOCKED task_id=%s reason=%s", task_id, diagnosis)
            return {
                "status": "blocked",
                "error": "Google requires human verification",
                "blocked_reason": "CAPTCHA / bot verification detected",
                "recovery_strategy": "blocked",
                "recovery_record": record.model_dump(),
            }

        record = RecoveryRecord(
            failure_type=failure_type,
            diagnosis=diagnosis,
            strategy=strategy,
            retry_count=retry_count + 1,
            max_retries=self.max_total_retries,
            outcome="retry",
        )
        self._save_record(task_id, record)

        logger.info(
            "RECOVERY task_id=%s failure_type=%s strategy=%s retry=%d/%d diagnosis=%s",
            task_id, failure_type, strategy, retry_count + 1, self.max_total_retries, diagnosis,
        )

        # Return state updates — the graph will route based on recovery_strategy
        return {
            "retry_count": retry_count + 1,
            "status": "running",
            "error": None,
            "recovery_strategy": strategy,
            "recovery_record": record.model_dump(),
        }

    def get_recovery_history(self, task_id: str) -> list[RecoveryRecord]:
        """Return all recovery records for a task."""
        return self._recovery_history.get(task_id, [])

    def _save_record(self, task_id: str, record: RecoveryRecord) -> None:
        """Append a recovery record to the task's history."""
        if task_id not in self._recovery_history:
            self._recovery_history[task_id] = []
        self._recovery_history[task_id].append(record)


recovery_engine = RecoveryEngine()

