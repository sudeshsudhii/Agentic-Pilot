"""Gmail plugin for Pilot.

Supports composing and sending email intents. Sending is high risk and approval
gated; the MVP prepares message data without sending email.
"""

from backend.llm.parser import ParsedIntent
from backend.plugins.base import PluginBase, PluginResult


class GmailPlugin(PluginBase):
    """Built-in Gmail automation plugin."""

    plugin_id = "gmail"
    name = "Gmail"
    sites = ["gmail.com", "mail.google.com"]
    actions = ["compose", "send_email"]
    risk_levels = {"compose": "medium", "send_email": "high"}

    def validate_params(self, intent: ParsedIntent) -> list[str]:
        """Validate recipient and email content requirements."""

        errors: list[str] = []
        if intent.action not in self.actions:
            errors.append("Gmail plugin supports compose and send_email actions.")
        if not intent.target:
            errors.append("Recipient email address is required.")
        return errors

    def get_selector_hints(self, action: str) -> dict[str, list[str]]:
        """Return selector hints for Gmail compose controls."""

        return {
            "compose": ["Compose"],
            "to": ["To", "Recipients"],
            "subject": ["Subject"],
            "body": ["Message Body"],
            "send": ["Send"],
        }

    async def execute(self, intent: ParsedIntent) -> PluginResult:
        """Prepare a Gmail action without sending email."""

        errors = self.validate_params(intent)
        if errors:
            return PluginResult(success=False, message="; ".join(errors))
        return PluginResult(
            success=True,
            message="Gmail message prepared; live send requires approval and an authenticated session.",
            data={"recipient": intent.target, "content": intent.content, "dry_run": True},
            requires_approval=intent.action == "send_email",
        )
