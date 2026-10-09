"""Comprehensive unit and integration test suite for Gemini LLM provider,
configuration, routing, structured output, error handling, hybrid fallback,
and desktop planner integration in Agentic Pilot.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import os
import pytest
from pydantic import BaseModel, Field

from backend.config import PilotConfig, get_config
from backend.agent.desktop_nodes import desktop_plan_action_node
from backend.agent.graph import build_graph
from backend.agent.state import AgentState
from backend.desktop.models import DesktopAction, DesktopActionType
from backend.llm.base import (
    BaseLLMProvider,
    GeminiAuthenticationError,
    GeminiRateLimitError,
    GeminiResponseError,
    GeminiTimeoutError,
    LLMProviderError,
    MissingGeminiApiKeyError,
)
from backend.llm.gateway import LLMGateway, OllamaGateway, get_llm_provider
from backend.llm.gemini import GeminiGateway
from backend.llm.hybrid import HybridLLMProvider
from backend.llm.router import model_router


class SamplePlanSchema(BaseModel):
    step: int
    action: str
    target: str


# ---------------------------------------------------------------------------
# 1. Configuration & API Key Tests
# ---------------------------------------------------------------------------

def test_gemini_config_defaults_and_env_aliases():
    """Verify Gemini configuration defaults and environment variable resolution."""
    with patch.dict(os.environ, {
        "LLM_PROVIDER": "gemini",
        "GEMINI_API_KEY": "test_env_key_12345",
        "GEMINI_MODEL": "gemini-2.5-flash",
        "GEMINI_TEMPERATURE": "0.1",
        "GEMINI_TIMEOUT_SECONDS": "30",
    }, clear=False):
        cfg = PilotConfig()
        assert cfg.llm_provider == "gemini"
        assert cfg.gemini_api_key == "test_env_key_12345"
        assert cfg.gemini_model == "gemini-2.5-flash"
        assert cfg.gemini_temperature == 0.1
        assert cfg.gemini_timeout_seconds == 30


def test_missing_api_key_raises_clear_error():
    """Verify that MissingGeminiApiKeyError is raised when GEMINI_API_KEY is absent."""
    cfg = PilotConfig(gemini_api_key=None)
    with patch.dict(os.environ, {}, clear=True):
        # Explicitly remove any GEMINI_API_KEY from env
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ.pop("PILOT_GEMINI_API_KEY", None)
        gateway = GeminiGateway(config=cfg)
        with pytest.raises(MissingGeminiApiKeyError) as exc_info:
            gateway._get_api_key()
        assert "GEMINI_API_KEY is missing" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 2. Provider Selection Tests
# ---------------------------------------------------------------------------

def test_provider_selection_gemini():
    """Verify get_llm_provider returns GeminiGateway when LLM_PROVIDER=gemini."""
    cfg = PilotConfig(llm_provider="gemini", gemini_api_key="test_key")
    provider = get_llm_provider(cfg)
    assert isinstance(provider, GeminiGateway)
    assert provider.provider_name == "gemini"


def test_provider_selection_ollama():
    """Verify get_llm_provider returns OllamaGateway when LLM_PROVIDER=ollama."""
    cfg = PilotConfig(llm_provider="ollama")
    provider = get_llm_provider(cfg)
    assert isinstance(provider, OllamaGateway)
    assert provider.provider_name == "ollama"


def test_provider_selection_hybrid():
    """Verify get_llm_provider returns HybridLLMProvider when LLM_PROVIDER=hybrid."""
    cfg = PilotConfig(llm_provider="hybrid", gemini_api_key="test_key")
    provider = get_llm_provider(cfg)
    assert isinstance(provider, HybridLLMProvider)
    assert provider.provider_name == "hybrid"


def test_llm_gateway_proxy():
    """Verify LLMGateway correctly proxies to the active provider."""
    cfg = PilotConfig(llm_provider="gemini", gemini_api_key="test_key")
    gw = LLMGateway(cfg)
    assert gw.provider_name == "gemini"


# ---------------------------------------------------------------------------
# 3. Model Router with Cloud Provider
# ---------------------------------------------------------------------------

def test_model_router_with_gemini_provider():
    """Verify GeminiGateway maps local model overrides to gemini-2.5-flash."""
    gateway = GeminiGateway(config=PilotConfig(gemini_api_key="test_key", gemini_model="gemini-2.5-flash"))
    assert gateway._resolve_model("qwen2.5:7b") == "gemini-2.5-flash"
    assert gateway._resolve_model("moondream") == "gemini-2.5-flash"
    assert gateway._resolve_model("deepseek-r1:1.5b") == "gemini-2.5-flash"
    assert gateway._resolve_model("custom-gemini-pro") == "custom-gemini-pro"


# ---------------------------------------------------------------------------
# 4. Gemini Text & Structured Generation Tests (Mocked API)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gemini_complete_text():
    """Verify Gemini complete() returns generated text and records telemetry."""
    cfg = PilotConfig(gemini_api_key="fake_test_key_abc", gemini_model="gemini-2.5-flash")
    gateway = GeminiGateway(config=cfg)

    mock_resp = MagicMock()
    mock_resp.text = "Navigation confirmed."
    mock_resp.usage_metadata = MagicMock(prompt_token_count=15, candidates_token_count=5)

    with patch.object(gateway, "_client_instance") as mock_client_factory:
        mock_client = MagicMock()
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_resp)
        mock_client_factory.return_value = mock_client

        result = await gateway.complete(system="System instructions", user="User request")
        assert result == "Navigation confirmed."
        assert gateway._last_input_tokens == 15
        assert gateway._last_output_tokens == 5


@pytest.mark.asyncio
async def test_gemini_complete_structured():
    """Verify Gemini complete_structured() returns parsed Pydantic model."""
    cfg = PilotConfig(gemini_api_key="fake_test_key_abc", gemini_model="gemini-2.5-flash")
    gateway = GeminiGateway(config=cfg)

    mock_resp = MagicMock()
    mock_resp.text = '{"step": 1, "action": "click_element", "target": "desktop-el-001"}'
    mock_resp.usage_metadata = MagicMock(prompt_token_count=30, candidates_token_count=18)

    with patch.object(gateway, "_client_instance") as mock_client_factory:
        mock_client = MagicMock()
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_resp)
        mock_client_factory.return_value = mock_client

        model_res = await gateway.complete_structured(
            system="Planner system",
            user="Plan next step",
            schema=SamplePlanSchema,
        )
        assert isinstance(model_res, SamplePlanSchema)
        assert model_res.step == 1
        assert model_res.action == "click_element"
        assert model_res.target == "desktop-el-001"


# ---------------------------------------------------------------------------
# 5. Gemini Error Handling Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gemini_authentication_error_no_retry():
    """Verify 401/403 or invalid API key immediately raises GeminiAuthenticationError."""
    cfg = PilotConfig(gemini_api_key="invalid_key", max_retry_count=3)
    gateway = GeminiGateway(config=cfg)

    with patch.object(gateway, "_client_instance") as mock_client_factory:
        mock_client = MagicMock()
        mock_client.aio.models.generate_content = AsyncMock(side_effect=Exception("API_KEY_INVALID: 401 Unauthorized"))
        mock_client_factory.return_value = mock_client

        with pytest.raises(GeminiAuthenticationError):
            await gateway.complete(system="sys", user="user")

        # Must not retry on permanent auth failure
        assert mock_client.aio.models.generate_content.call_count == 1


@pytest.mark.asyncio
async def test_gemini_timeout_handling():
    """Verify request timeout raises GeminiTimeoutError."""
    cfg = PilotConfig(gemini_api_key="valid_key", gemini_timeout_seconds=1, max_retry_count=0)
    gateway = GeminiGateway(config=cfg)

    with patch.object(gateway, "_client_instance") as mock_client_factory:
        mock_client = MagicMock()
        async def slow_call(*args, **kwargs):
            await asyncio.sleep(2.0)
            return MagicMock(text="late")

        mock_client.aio.models.generate_content = slow_call
        mock_client_factory.return_value = mock_client

        with pytest.raises(GeminiTimeoutError):
            await gateway.complete(system="sys", user="user")


@pytest.mark.asyncio
async def test_gemini_invalid_structured_output_exhaustion():
    """Verify malformed JSON responses raise GeminiResponseError after max retries."""
    cfg = PilotConfig(gemini_api_key="valid_key", max_retry_count=1)
    gateway = GeminiGateway(config=cfg)

    mock_resp = MagicMock()
    mock_resp.text = "NOT JSON AT ALL"

    with patch.object(gateway, "_client_instance") as mock_client_factory:
        mock_client = MagicMock()
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_resp)
        mock_client_factory.return_value = mock_client

        with pytest.raises(GeminiResponseError):
            await gateway.complete_structured(system="sys", user="user", schema=SamplePlanSchema)


# ---------------------------------------------------------------------------
# 6. Hybrid Fallback Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_hybrid_fallback_to_ollama():
    """Verify HybridLLMProvider catches Gemini failure and seamlessly uses Ollama."""
    cfg = PilotConfig(llm_provider="hybrid", gemini_api_key="valid_key")
    hybrid = HybridLLMProvider(config=cfg)

    # Gemini fails, Ollama succeeds
    hybrid.gemini.complete = AsyncMock(side_effect=Exception("Gemini network error"))
    hybrid.ollama.complete = AsyncMock(return_value="Ollama response")

    result = await hybrid.complete(system="sys", user="user")
    assert result == "Ollama response"
    assert hybrid.gemini.complete.call_count == 1
    assert hybrid.ollama.complete.call_count == 1


# ---------------------------------------------------------------------------
# 7. Desktop Planner Integration & Safety Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_desktop_planner_with_gemini_provider():
    """Verify desktop_plan_action_node uses Gemini and produces typed DesktopAction."""
    state: AgentState = {
        "task_id": "test-task-1",
        "input_text": "Open Windows Settings",
        "status": "running",
        "current_step_index": 1,
        "desktop_observation": {
            "active_window": {"title": "Desktop"},
            "elements": [
                {"id": "desktop-el-01", "name": "Start", "role": "button", "control_type": "ButtonControl"}
            ],
        },
    }

    mock_action = DesktopAction(
        action_type=DesktopActionType.LAUNCH_APPLICATION,
        application="settings",
        reasoning="Launching Windows Settings app",
    )

    with patch("backend.agent.desktop_nodes.get_llm_provider") as mock_get_provider:
        mock_gw = MagicMock()
        mock_gw.complete_structured = AsyncMock(return_value=mock_action)
        mock_get_provider.return_value = mock_gw

        result = await desktop_plan_action_node(state)
        assert result["desktop_action"]["action_type"] == "launch_application"
        assert result["desktop_action"]["application"] == "settings"


@pytest.mark.asyncio
async def test_desktop_planner_completion_authority_enforced():
    """Verify planner cannot directly return 'complete' (Requirement 10)."""
    state: AgentState = {
        "task_id": "test-task-2",
        "input_text": "Turn on Bluetooth",
        "status": "running",
        "desktop_observation": {"elements": []},
    }

    # Simulate an LLM attempting to set action_type or text to "complete"
    fake_action = DesktopAction(
        action_type=DesktopActionType.WAIT,
        reasoning="Task is complete",
    )
    # Monkeypatch action_type to simulate a raw string "complete"
    fake_action.action_type = "complete"  # type: ignore

    with patch("backend.agent.desktop_nodes.get_llm_provider") as mock_get_provider:
        mock_gw = MagicMock()
        mock_gw.complete_structured = AsyncMock(return_value=fake_action)
        mock_get_provider.return_value = mock_gw

        result = await desktop_plan_action_node(state)
        # Must be overridden to request_reobservation
        assert result["desktop_action"]["action_type"] == "request_reobservation"


@pytest.mark.asyncio
async def test_desktop_planner_rejects_arbitrary_code():
    """Verify planner rejects PowerShell, CMD, Python commands (Requirement 9)."""
    state: AgentState = {
        "task_id": "test-task-3",
        "input_text": "Open something",
        "status": "running",
        "desktop_observation": {"elements": []},
    }

    malicious_action = DesktopAction(
        action_type=DesktopActionType.TYPE_TEXT,
        text="powershell -Command Remove-Item -Force C:\\test",
        reasoning="Attempting script execution",
    )

    with patch("backend.agent.desktop_nodes.get_llm_provider") as mock_get_provider:
        mock_gw = MagicMock()
        mock_gw.complete_structured = AsyncMock(return_value=malicious_action)
        mock_get_provider.return_value = mock_gw

        result = await desktop_plan_action_node(state)
        # Must be rejected and safe request_reobservation returned
        assert result["desktop_action"]["action_type"] == "request_reobservation"


@pytest.mark.asyncio
async def test_desktop_planner_bluetooth_already_on_preservation():
    """Verify if Bluetooth is already ON, planner does NOT click toggle (Requirements 8 & 14)."""
    state: AgentState = {
        "task_id": "test-task-4",
        "input_text": "Open Windows Settings and make sure Bluetooth is ON",
        "status": "running",
        "desktop_observation": {
            "elements": [
                {
                    "id": "desktop-el-bt",
                    "name": "Bluetooth",
                    "role": "toggle",
                    "control_type": "ButtonControl",
                    "toggle_state": "On",
                }
            ]
        },
    }

    # LLM wrongly proposes clicking the toggle
    click_action = DesktopAction(
        action_type=DesktopActionType.CLICK_ELEMENT,
        target_id="desktop-el-bt",
        reasoning="Click Bluetooth toggle",
    )

    with patch("backend.agent.desktop_nodes.get_llm_provider") as mock_get_provider:
        mock_gw = MagicMock()
        mock_gw.complete_structured = AsyncMock(return_value=click_action)
        mock_get_provider.return_value = mock_gw

        result = await desktop_plan_action_node(state)
        # Must be overridden to wait to preserve On state!
        assert result["desktop_action"]["action_type"] == "wait"
        assert "already ON" in result["desktop_action"]["reasoning"]


# ---------------------------------------------------------------------------
# 8. Graph Architectural Routing Tests (Requirement 15)
# ---------------------------------------------------------------------------

def test_graph_desktop_recovery_routes_to_desktop_observe():
    """Verify desktop recovery loops back to desktop_observe, NOT extract_dom (Requirement 15)."""
    graph = build_graph()
    assert graph is not None

    # Inspect conditional branches in the graph
    branches = graph.builder.branches.get("error_recovery", {})
    assert len(branches) > 0

    # Test the branch routing function directly on desktop state
    branch = list(branches.values())[0]
    routing_fn = branch.path.func

    desktop_retry_state: AgentState = {
        "task_id": "t1",
        "input_text": "Settings task",
        "current_environment": "desktop",
        "status": "running",
    }
    assert routing_fn(desktop_retry_state) == "desktop_observe"

    browser_retry_state: AgentState = {
        "task_id": "t2",
        "input_text": "Browser task",
        "current_environment": "browser",
        "status": "running",
    }
    assert routing_fn(browser_retry_state) == "extract_dom"

    desktop_fail_state: AgentState = {
        "task_id": "t3",
        "input_text": "Settings task",
        "current_environment": "desktop",
        "status": "failed",
    }
    assert routing_fn(desktop_fail_state) == "desktop_complete"


def test_graph_mixed_task_step_aware():
    """Verify mixed task routes based on current step environment (Requirement 15)."""
    from backend.agent.environment import EnvironmentType, classify_environment
    from backend.llm.parser import TaskPlan, TaskStep

    browser_step = TaskStep(step_index=1, description="Navigate to https://example.com", action_type="navigate")
    desktop_step = TaskStep(step_index=2, description="Open Notepad and paste", action_type="launch_application")

    assert classify_environment(browser_step.description) == EnvironmentType.BROWSER
    assert classify_environment(desktop_step.description) == EnvironmentType.DESKTOP
