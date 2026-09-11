"""End-to-end integration tests for Multi-Model Routing, Execution Provenance, and Code Execution."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest

from backend.agent.code_executor import CodeExecutor
from backend.agent.nodes import error_recovery_node, parse_intent_node, plan_action_node
from backend.agent.state import AgentState
from backend.evidence.manager import ExecutionRecord, EvidenceManager
from backend.llm.parser import ActionManifest, ActionResult, ParsedIntent, PlannedAction
from backend.telemetry.tracer import TelemetryTracer


def test_execution_record_model_provenance(tmp_path: Path):
    """Verify ExecutionRecord correctly persists model routing provenance."""
    record = ExecutionRecord(
        task_id="task_test_provenance",
        step_id="S001",
        step_index=1,
        action={"type": "click", "element_id": "btn_submit"},
        before_state={"url": "http://test.local"},
        execution_result={"success": True},
        after_state={"url": "http://test.local/done"},
        model="qwen2.5:7b",
        model_role="reasoning",
        routing_reason="Task decomposition complexity required reasoning specialist",
        duration_ms=120,
    )
    assert record.model == "qwen2.5:7b"
    assert record.model_role == "reasoning"
    assert "reasoning specialist" in record.routing_reason

    mgr = EvidenceManager(evidence_dir=tmp_path)
    file_path = mgr.save_execution_record(record)
    assert Path(file_path).exists()

    loaded = mgr.load_task_records("task_test_provenance")
    assert len(loaded) == 1
    assert loaded[0].model == "qwen2.5:7b"
    assert loaded[0].model_role == "reasoning"
    assert loaded[0].routing_reason == record.routing_reason


def test_telemetry_tracer_multi_model_metrics(tmp_path: Path):
    """Verify tracer records model routing events and aggregates metrics correctly."""
    tracer = TelemetryTracer()
    tracer.log_dir = tmp_path
    tracer.trace_file = tmp_path / "traces.jsonl"

    tracer.record_model_routing("t1", "deepseek-r1:1.5b", "lightweight", "Intent parsing", model_switch=False)
    tracer.record_model_routing("t1", "qwen2.5:7b", "reasoning", "Complex planning", model_switch=True)
    tracer.record_model_routing("t1", "moondream", "vision", "Screenshot analysis", model_switch=True)
    tracer.record_model_routing("t1", "qwen2.5:1.5b", "general", "Fallback to base", model_switch=True, fallback_used=True)

    metrics = tracer.get_aggregated_metrics(["t1"])
    assert metrics["total_model_routings"] == 4
    assert metrics["model_switch_count"] == 3
    assert metrics["model_fallback_rate"] == 25.0
    assert metrics["model_usage_by_role"]["lightweight"] == 1
    assert metrics["model_usage_by_role"]["reasoning"] == 1
    assert metrics["model_usage_by_role"]["vision"] == 1
    assert metrics["model_usage_by_role"]["general"] == 1


def test_code_executor_file_operations(tmp_path: Path):
    """Verify CodeExecutor safely inspects, modifies, and validates Python syntax."""
    executor = CodeExecutor(workspace_root=tmp_path)
    test_file = tmp_path / "script.py"

    # Write code
    initial_code = "def add(a, b):\n    return a + b\n"
    res_write = executor.write_file(test_file, initial_code)
    assert res_write.success is True
    assert executor.read_file(test_file) == initial_code

    # Validate syntax
    diag = executor.validate_syntax(test_file)
    assert diag["valid"] is True

    # Replace snippet
    res_replace = executor.replace_snippet(test_file, "return a + b", "return a + b + 1")
    assert res_replace.success is True
    assert "return a + b + 1" in executor.read_file(test_file)

    # Invalid syntax check
    executor.write_file(test_file, "def broken_code(\n")
    diag_broken = executor.validate_syntax(test_file)
    assert diag_broken["valid"] is False
    assert "error" in diag_broken


@pytest.mark.asyncio
async def test_parse_intent_node_model_routing():
    """Verify parse_intent_node attaches routed model provenance to state."""
    state: AgentState = {
        "task_id": "test_routing_task",
        "input_text": "navigate to https://wikipedia.org",
        "parsed_intent": None,
        "current_url": None,
        "action_manifest": None,
        "action_history": [],
        "retry_count": 0,
        "status": "running",
        "approval_id": None,
        "error": None,
        "result": None,
        "plugin_id": None,
        "llm_call_count": 0,
        "planned_action": None,
        "approved": False,
        "navigation_succeeded": False,
        "session_id": None,
        "task_plan": None,
        "current_step_index": 1,
        "retrieved_knowledge": [],
        "retrieved_memories": [],
        "retrieval_metadata": {},
        "selected_model": None,
        "model_role": None,
        "routing_reason": None,
        "model_switch": False,
    }

    mock_intent = ParsedIntent(action="navigate", site="https://wikipedia.org", risk_level="low", reasoning="test")

    with patch("backend.llm.gateway.OllamaGateway.complete_structured", new_callable=AsyncMock) as mock_complete:
        mock_complete.return_value = mock_intent
        result = await parse_intent_node(state)

        assert "selected_model" in result
        assert result["selected_model"] is not None
        assert result["model_role"] in ("lightweight", "general", "reasoning")
        assert "routing_reason" in result


@pytest.mark.asyncio
async def test_plan_action_node_model_routing():
    """Verify plan_action_node selects model and passes model_override to gateway."""
    manifest = ActionManifest(
        url="https://wikipedia.org",
        page_title="Wikipedia",
        page_state="ready",
        interactive_elements=[],
    )
    state: AgentState = {
        "task_id": "test_plan_routing",
        "input_text": "write python script to clean data",
        "parsed_intent": ParsedIntent(action="code", site="unknown", risk_level="low", reasoning="coding task"),
        "current_url": "https://wikipedia.org",
        "action_manifest": manifest,
        "action_history": [],
        "retry_count": 0,
        "status": "running",
        "approval_id": None,
        "error": None,
        "result": None,
        "plugin_id": None,
        "llm_call_count": 0,
        "planned_action": None,
        "approved": False,
        "navigation_succeeded": True,
        "session_id": None,
        "task_plan": None,
        "current_step_index": 1,
        "retrieved_knowledge": [],
        "retrieved_memories": [],
        "retrieval_metadata": {},
        "selected_model": None,
        "model_role": None,
        "routing_reason": None,
        "model_switch": False,
    }

    mock_action = PlannedAction(action_type="complete", reasoning="Coding completed")

    with patch("backend.llm.gateway.OllamaGateway.complete_structured", new_callable=AsyncMock) as mock_complete:
        mock_complete.return_value = mock_action
        result = await plan_action_node(state)

        assert result["model_role"] == "coding"
        assert "coder" in result["selected_model"] or "qwen" in result["selected_model"]
        assert mock_complete.called
        # Verify model_override keyword argument was passed
        _, kwargs = mock_complete.call_args
        assert kwargs.get("model_override") == result["selected_model"]
