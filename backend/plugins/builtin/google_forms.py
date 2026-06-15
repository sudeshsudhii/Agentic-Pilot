"""Google Forms plugin for Pilot.

Supports filling public Google Forms. Submitting forms is high risk and remains
approval-gated by the task runner.
"""

from backend.llm.parser import ParsedIntent
from backend.plugins.base import PluginBase, PluginResult


class GoogleFormsPlugin(PluginBase):
    """Built-in Google Forms automation plugin."""

    plugin_id = "google_forms"
    name = "Google Forms"
    sites = ["docs.google.com/forms", "forms.gle"]
    actions = ["fill_form", "submit_form"]
    risk_levels = {"fill_form": "medium", "submit_form": "high"}

    def validate_params(self, intent: ParsedIntent) -> list[str]:
        """Validate that form fill content exists."""

        if intent.action not in self.actions:
            return ["Google Forms plugin supports fill_form and submit_form actions."]
        if not intent.content:
            return ["Form field content is required."]
        return []

    def get_selector_hints(self, action: str) -> dict[str, list[str]]:
        """Return selector hints for common Google Forms controls."""

        return {
            "text_field": ["Short answer text", "Paragraph"],
            "submit": ["Submit"],
        }

    async def execute(self, intent: ParsedIntent) -> PluginResult:
        """Prepare a Google Form fill action without submitting."""

        errors = self.validate_params(intent)
        if errors:
            return PluginResult(success=False, message="; ".join(errors))
        return PluginResult(
            success=True,
            message="Google Form fill prepared; submission requires explicit approval.",
            data={"content": intent.content, "dry_run": True},
            requires_approval=intent.action == "submit_form",
        )
