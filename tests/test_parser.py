"""Tests for Pilot intent parsing and JSON cleanup."""

from backend.llm.parser import ParsedIntent, heuristic_parse_intent, parse_model_response


def test_heuristic_parser_marks_post_high_risk() -> None:
    """Twitter posting should be parsed as a high-risk action."""

    intent = heuristic_parse_intent("Post this to Twitter: Just shipped Pilot")
    assert intent.action == "post"
    assert intent.site == "twitter.com"
    assert intent.risk_level == "high"
    assert intent.content == "Just shipped Pilot"


def test_heuristic_parser_marks_search_low_risk() -> None:
    """Search instructions should be low risk and capture a query."""

    intent = heuristic_parse_intent("Search Google for playwright python")
    assert intent.action == "search"
    assert intent.risk_level == "low"
    assert intent.target == "playwright python"


def test_parse_model_response_strips_code_fences() -> None:
    """Structured parsing should tolerate common LLM JSON wrapping."""

    parsed = parse_model_response(
        """```json
        {"action":"search","site":"google.com","content":null,"target":"AI agents","attachments":[],"risk_level":"low","confidence":0.9,"reasoning":"Clear search"}
        ```""",
        ParsedIntent,
    )
    assert isinstance(parsed, ParsedIntent)
    assert parsed.site == "google.com"
