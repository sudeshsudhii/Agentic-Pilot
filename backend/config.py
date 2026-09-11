"""Application settings for the Pilot backend."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PilotConfig(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_prefix="PILOT_", extra="ignore")

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:1.5b"
    ollama_vision_model: str = "moondream"
    db_path: str = "~/.pilot/data.db"
    data_dir: str = "~/.pilot/data"
    log_dir: str = "~/.pilot/logs"

    server_port: int = Field(default=8765, ge=1, le=65535)
    headless_browser: bool = False
    auto_approve_low_risk: bool = True
    approval_timeout_seconds: int = Field(default=10, ge=1)
    max_retry_count: int = Field(default=3, ge=0)
    session_ttl_hours: int = Field(default=24, ge=1)
    debug_mode: bool = False
    max_task_duration_minutes: int = Field(default=5, ge=1)
    browser_pool_size: int = Field(default=3, ge=1)
    keep_browser_open: bool = True
    browser_idle_timeout_minutes: int = Field(default=15, ge=1)
    app_version: str = "1.0.0"

    # --- Ablation Feature Flags (Phase 10 / R15) ---
    enable_evidence: bool = True
    enable_verification: bool = True
    enable_recovery: bool = True
    enable_memory: bool = True
    enable_rag: bool = True
    enable_multi_model: bool = True

    # --- Multi-Model Routing Config ---
    model_routing_strategy: str = "dynamic"  # "dynamic", "static", "single"
    model_reasoning: str = "qwen2.5:7b"
    model_vision: str = "moondream"
    model_coding: str = "qwen2.5-coder:3b"
    model_lightweight: str = "deepseek-r1:1.5b"
    model_fallback: str = "qwen2.5:1.5b"
    model_switch_cooldown_steps: int = Field(default=1, ge=0)
    model_candidates_by_role: dict[str, list[str]] = Field(
        default_factory=lambda: {
            "planner": ["qwen3.5:2b", "qwen2.5:7b", "deepseek-r1:1.5b"],
            "executor": ["qwen2.5:1.5b", "qwen2.5:7b"],
            "vision": ["qwen3-vl:2b", "moondream"],
            "coder": ["qwen2.5-coder:3b", "qwen2.5-coder:1.5b"],
            "lightweight": ["deepseek-r1:1.5b", "qwen3.5:2b", "qwen2.5:1.5b"],
            "recovery": ["qwen2.5:7b", "qwen3.5:2b"],
            "general": ["qwen2.5:1.5b", "qwen2.5:7b"],
            "fallback": ["qwen2.5:1.5b"],
        }
    )
    task_context_token_budget: int = Field(default=3500, ge=500)
    embedding_cache_enabled: bool = True
    vision_cache_enabled: bool = True


    # --- RAG Subsystem Config ---
    rag_knowledge_collection: str = "pilot_knowledge"
    rag_top_k: int = Field(default=5, ge=1)
    rag_similarity_threshold: float = Field(default=0.45, ge=0.0, le=1.0)
    rag_hybrid_search: bool = False
    rag_reranking: bool = False
    rag_max_context_tokens: int = Field(default=2000, ge=100)
    rag_cache_enabled: bool = True
    rag_cache_ttl_seconds: int = Field(default=3600, ge=1)
    rag_knowledge_dir: str = "~/.pilot/knowledge"
    rag_embedding_model: str = "all-minilm"

    # --- Privacy Audit (Phase 9 / R12) ---
    privacy_audit_enabled: bool = True
    privacy_audit_log: str = "~/.pilot/logs/privacy_audit.jsonl"

    # --- Experiment Config (Phase 10 / R14) ---
    experiment_mode: bool = False
    experiment_output_dir: str = "~/.pilot/experiments"



@lru_cache
def get_config() -> PilotConfig:
    """Return the cached application configuration."""

    return PilotConfig()
