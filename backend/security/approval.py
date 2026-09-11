"""Risk scoring and approval-gate helpers for Pilot."""

from backend.llm.parser import ParsedIntent

HIGH_RISK_LEVELS = {"high", "critical"}


def requires_approval(intent: ParsedIntent | dict | None) -> bool:
    """Return True when a parsed intent requires explicit human approval."""
    if not intent:
        return False
    action = intent.get("action") if isinstance(intent, dict) else intent.action
    risk_level = intent.get("risk_level") if isinstance(intent, dict) else intent.risk_level
    if action in {"post", "send_email", "purchase", "delete", "transfer"}:
        return True
    return risk_level in HIGH_RISK_LEVELS


def build_approval_prompt(intent: ParsedIntent | dict) -> str:
    """Build a concise human-readable approval prompt."""
    action = intent.get("action", "unknown") if isinstance(intent, dict) else intent.action
    risk_level = intent.get("risk_level", "medium") if isinstance(intent, dict) else intent.risk_level
    site = intent.get("site", "website") if isinstance(intent, dict) else (intent.site or "website")

    return f"Approve {risk_level} action '{action}' on {site}?"
