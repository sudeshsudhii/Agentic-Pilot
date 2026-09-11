"""Experimentation and ablation framework for Agentic Pilot (Phase 10 / R14).

Provides automated experimental evaluation and ablation benchmarking
for research comparisons.
"""

from backend.experiment.config import ABLATION_PRESETS, ExperimentConfig
from backend.experiment.runner import ExperimentRunner

__all__ = ["ABLATION_PRESETS", "ExperimentConfig", "ExperimentRunner"]
