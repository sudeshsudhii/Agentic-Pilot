"""Tests for Pilot intent parsing and JSON cleanup."""

from backend.llm.parser import ParsedIntent, parse_model_response


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
