"""Local language model integration package for Pilot."""

from backend.llm.analyzer import CapabilityAnalyzer, TaskCapabilityRequirements, capability_analyzer
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
from backend.llm.parser import ActionResult, ParsedIntent, PlannedAction, TaskPlan, TaskStep
from backend.llm.registry import ModelCapability, ModelMetadata, ModelRegistry, ModelRole, model_registry
from backend.llm.router import ModelRouter, RoutingDecision, model_router

__all__ = [
    "BaseLLMProvider",
    "GeminiGateway",
    "HybridLLMProvider",
    "LLMGateway",
    "OllamaGateway",
    "get_llm_provider",
    "LLMProviderError",
    "MissingGeminiApiKeyError",
    "GeminiAuthenticationError",
    "GeminiRateLimitError",
    "GeminiTimeoutError",
    "GeminiResponseError",
    "ParsedIntent",
    "PlannedAction",
    "ActionResult",
    "TaskPlan",
    "TaskStep",
    "ModelCapability",
    "ModelRole",
    "ModelMetadata",
    "ModelRegistry",
    "model_registry",
    "CapabilityAnalyzer",
    "capability_analyzer",
    "TaskCapabilityRequirements",
    "ModelRouter",
    "RoutingDecision",
    "model_router",
]

