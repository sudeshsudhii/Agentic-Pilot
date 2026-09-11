"""Ablation configurations and experiment definitions for Agentic Pilot (Phase 10 / R14)."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field

from backend.config import PilotConfig


class ExperimentConfig(BaseModel):
    """Configuration for a single experimental evaluation run."""

    name: str
    description: str
    pilot_config_overrides: dict[str, Any] = Field(default_factory=dict)
    models: list[str] = Field(default_factory=lambda: ["qwen2.5:7b"])
    benchmark_tasks: list[str] = Field(default_factory=list)
    runs_per_task: int = 1


# Standard ablation study presets for the research paper
ABLATION_PRESETS: dict[str, ExperimentConfig] = {
    "full_framework": ExperimentConfig(
        name="full_framework",
        description="Full Agentic Pilot system with Multi-Model routing, RAG, Evidence, Verification, Recovery, and Memory enabled",
        pilot_config_overrides={
            "enable_multi_model": True,
            "model_routing_strategy": "dynamic",
            "enable_rag": True,
            "enable_evidence": True,
            "enable_verification": True,
            "enable_recovery": True,
            "enable_memory": True,
        },
    ),
    "single_model": ExperimentConfig(
        name="single_model",
        description="Ablation: Single general model handles all roles without multi-model routing",
        pilot_config_overrides={
            "enable_multi_model": False,
            "model_routing_strategy": "single",
            "enable_rag": True,
            "enable_evidence": True,
            "enable_verification": True,
            "enable_recovery": True,
            "enable_memory": True,
        },
    ),
    "multi_model_static": ExperimentConfig(
        name="multi_model_static",
        description="Ablation: Multi-model architecture with static role-to-model configuration",
        pilot_config_overrides={
            "enable_multi_model": True,
            "model_routing_strategy": "static",
            "enable_rag": True,
            "enable_evidence": True,
            "enable_verification": True,
            "enable_recovery": True,
            "enable_memory": True,
        },
    ),
    "multi_model_dynamic": ExperimentConfig(
        name="multi_model_dynamic",
        description="Multi-model architecture with dynamic 4-stage capability-aware routing",
        pilot_config_overrides={
            "enable_multi_model": True,
            "model_routing_strategy": "dynamic",
            "enable_rag": True,
            "enable_evidence": True,
            "enable_verification": True,
            "enable_recovery": True,
            "enable_memory": True,
        },
    ),
    "dynamic_routing_rag": ExperimentConfig(
        name="dynamic_routing_rag",
        description="Capability-aware routing with shared model-agnostic RAG knowledge retrieval",
        pilot_config_overrides={
            "enable_multi_model": True,
            "model_routing_strategy": "dynamic",
            "enable_rag": True,
            "enable_evidence": True,
            "enable_verification": True,
            "enable_recovery": True,
            "enable_memory": True,
        },
    ),
    "no_rag": ExperimentConfig(
        name="no_rag",
        description="Ablation: External domain knowledge RAG disabled (pure memory + LLM reasoning)",
        pilot_config_overrides={
            "enable_rag": False,
            "enable_evidence": True,
            "enable_verification": True,
            "enable_recovery": True,
            "enable_memory": True,
        },
    ),
    "rag_only_no_memory": ExperimentConfig(
        name="rag_only_no_memory",
        description="Ablation: Knowledge RAG enabled, but episodic execution memory disabled",
        pilot_config_overrides={
            "enable_rag": True,
            "enable_memory": False,
            "enable_evidence": True,
            "enable_verification": True,
            "enable_recovery": True,
        },
    ),
    "memory_only_no_rag": ExperimentConfig(
        name="memory_only_no_rag",
        description="Ablation: Episodic memory enabled, but external knowledge RAG disabled",
        pilot_config_overrides={
            "enable_rag": False,
            "enable_memory": True,
            "enable_evidence": True,
            "enable_verification": True,
            "enable_recovery": True,
        },
    ),
    "rag_hybrid": ExperimentConfig(
        name="rag_hybrid",
        description="RAG variant: Hybrid search combining vector embeddings with BM25/lexical term matching",
        pilot_config_overrides={
            "enable_rag": True,
            "rag_hybrid_search": True,
            "enable_evidence": True,
            "enable_verification": True,
            "enable_recovery": True,
            "enable_memory": True,
        },
    ),
    "rag_with_reranking": ExperimentConfig(
        name="rag_with_reranking",
        description="RAG variant: Vector retrieval with local neural/cross-encoder reranking layer",
        pilot_config_overrides={
            "enable_rag": True,
            "rag_reranking": True,
            "enable_evidence": True,
            "enable_verification": True,
            "enable_recovery": True,
            "enable_memory": True,
        },
    ),
    "no_evidence": ExperimentConfig(
        name="no_evidence",
        description="Ablation: Evidence collection and ExecutionRecord generation disabled",
        pilot_config_overrides={
            "enable_rag": True,
            "enable_evidence": False,
            "enable_verification": True,
            "enable_recovery": True,
            "enable_memory": True,
        },
    ),
    "no_verification": ExperimentConfig(
        name="no_verification",
        description="Ablation: Hard environment state verification disabled (blind LLM completion)",
        pilot_config_overrides={
            "enable_rag": True,
            "enable_evidence": True,
            "enable_verification": False,
            "enable_recovery": True,
            "enable_memory": True,
        },
    ),
    "no_recovery": ExperimentConfig(
        name="no_recovery",
        description="Ablation: Strategy escalation and recovery loops disabled (single failure aborts)",
        pilot_config_overrides={
            "enable_rag": True,
            "enable_evidence": True,
            "enable_verification": True,
            "enable_recovery": False,
            "enable_memory": True,
        },
    ),
    "no_memory": ExperimentConfig(
        name="no_memory",
        description="Ablation: Long-term episodic/strategy memory disabled (no historical retrieval)",
        pilot_config_overrides={
            "enable_rag": True,
            "enable_evidence": True,
            "enable_verification": True,
            "enable_recovery": True,
            "enable_memory": False,
        },
    ),
    "baseline_direct": ExperimentConfig(
        name="baseline_direct",
        description="Ablation: Pure baseline without Pilot framework enhancements",
        pilot_config_overrides={
            "enable_rag": False,
            "enable_evidence": False,
            "enable_verification": False,
            "enable_recovery": False,
            "enable_memory": False,
        },
    ),
}

# Standard test tasks for repeatable evaluation across domains
STANDARD_BENCHMARK_TASKS: list[str] = [
    # Browser automation tasks
    "Navigate to wikipedia.org and search for Artificial Intelligence",
    "Go to news.ycombinator.com and view top stories",
    "Navigate to github.com and inspect explore page",
    "Open google.com and search for local weather",
    # Vision & GUI tasks
    "Analyze screenshot of the dashboard and locate the search button",
    # Coding & diagnostics tasks
    "Write python script to calculate fibonacci numbers and check syntax",
    # Procedural RAG tasks
    "Follow standard operating procedure guide to configure deployment pipeline",
    # Recovery & resilience tasks
    "Recover from network timeout using alternative selector or replanning",
]

