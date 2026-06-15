"""Tests for built-in Pilot plugins."""

from backend.llm.parser import heuristic_parse_intent
from backend.plugins.runtime import plugin_registry


def test_plugin_registry_exposes_three_builtins() -> None:
    """The MVP should ship with Twitter, Gmail, and Google Forms plugins."""

    plugin_ids = {manifest.plugin_id for manifest in plugin_registry.list_manifests()}
    assert {"twitter", "gmail", "google_forms"}.issubset(plugin_ids)


def test_twitter_plugin_validates_content() -> None:
    """Twitter plugin should reject empty post content."""

    plugin = plugin_registry.get("twitter")
    assert plugin is not None
    intent = heuristic_parse_intent("Post to Twitter")
    errors = plugin.validate_params(intent)
    assert errors


def test_gmail_plugin_detects_send_email_risk() -> None:
    """Gmail send_email should stay high risk."""

    plugin = plugin_registry.get("gmail")
    assert plugin is not None
    assert plugin.get_risk_level("send_email") == "high"
