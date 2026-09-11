"""Local language model integration package for Pilot."""

from backend.llm.analyzer import CapabilityAnalyzer, TaskCapabilityRequirements, capability_analyzer
from backend.llm.gateway import OllamaGateway
from backend.llm.parser import ActionResult, ParsedIntent, PlannedAction, TaskPlan, TaskStep
from backend.llm.registry import ModelCapability, ModelMetadata, ModelRegistry, ModelRole, model_registry
from backend.llm.router import ModelRouter, RoutingDecision, model_router

__all__ = [
    "OllamaGateway",
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

