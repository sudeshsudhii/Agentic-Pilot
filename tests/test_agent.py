"""Unit tests for Pilot Agent."""

import pytest
from backend.llm.parser import heuristic_parse_intent

def test_heuristic_parse_intent():
    intent = heuristic_parse_intent("Go to x.com and post 'hello world'")
    assert intent.action == "post"
    assert intent.site == "x.com"
    assert intent.risk_level == "high"
    assert intent.content == "hello world"

def test_heuristic_parse_intent_safe():
    intent = heuristic_parse_intent("Search google for python programming")
    assert intent.action == "search"
    assert intent.site == "google.com"
    assert intent.risk_level == "low"
