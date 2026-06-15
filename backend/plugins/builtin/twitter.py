"""Twitter/X plugin for Pilot.

Supports preparing public posts. Publishing is high risk and requires approval.
The MVP implementation validates and prepares actions without posting unless a
future authenticated browser session executor is attached.
"""

from backend.llm.parser import ParsedIntent
from backend.plugins.base import PluginBase, PluginResult


class TwitterPlugin(PluginBase):
    """Built-in Twitter/X automation plugin."""

    plugin_id = "twitter"
    name = "Twitter/X"
    sites = ["twitter.com", "x.com"]
    actions = ["post"]
    risk_levels = {"post": "high"}

    def validate_params(self, intent: ParsedIntent) -> list[str]:
        """Validate the post content and action type."""

        errors: list[str] = []
        if intent.action != "post":
            errors.append("Twitter plugin only supports post actions.")
        if not intent.content:
            errors.append("Post content is required.")
        if intent.content and len(intent.content) > 280:
            errors.append("Post content must be 280 characters or fewer.")
        return errors

    def get_selector_hints(self, action: str) -> dict[str, list[str]]:
        """Return resilient selector hints for compose/post controls."""

        return {
            "compose": ["What's happening", "Post text", "Tweet text"],
            "submit": ["Post", "Tweet"],
        }

    async def execute(self, intent: ParsedIntent) -> PluginResult:
        """Prepare a Twitter/X post without performing a side effect."""

        errors = self.validate_params(intent)
        if errors:
            return PluginResult(success=False, message="; ".join(errors))
        return PluginResult(
            success=True,
            message="Twitter/X post prepared; live publishing requires an authenticated session.",
            data={"content": intent.content, "dry_run": True},
            requires_approval=True,
        )
