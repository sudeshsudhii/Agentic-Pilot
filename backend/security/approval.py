"""Risk scoring and approval-gate helpers for Pilot."""

from backend.llm.parser import ParsedIntent

HIGH_RISK_LEVELS = {"high", "critical"}


def requires_approval(intent: ParsedIntent) -> bool:
    """Return True when a parsed intent requires explicit human approval."""

    return intent.risk_level in HIGH_RISK_LEVELS


def build_approval_prompt(intent: ParsedIntent) -> str:
    """Build a concise human-readable approval prompt."""

    return (
        "Approve "
        + intent.risk_level
        + " action '"
        + intent.action
        + "' on "
        + intent.site
        + "?"
    )
