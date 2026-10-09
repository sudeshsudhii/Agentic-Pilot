"""Application settings for the Pilot backend."""

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PilotConfig(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="PILOT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM Provider Selection & Cloud Gemini Runtime ---
    llm_provider: str = Field(
        default="gemini",
        validation_alias=AliasChoices("LLM_PROVIDER", "PILOT_LLM_PROVIDER", "llm_provider"),
        description="Active LLM provider: 'gemini', 'ollama', or 'hybrid'",
    )
    gemini_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GEMINI_API_KEY", "PILOT_GEMINI_API_KEY", "gemini_api_key"),
        description="Google Gemini API key (loaded securely from environment)",
    )
    gemini_model: str = Field(
        default="gemini-3.5-flash-lite",
        validation_alias=AliasChoices("GEMINI_MODEL", "PILOT_GEMINI_MODEL", "gemini_model"),
        description="Gemini model name",
    )
    gemini_temperature: float = Field(
        default=0.1,
        ge=0.0,
        le=2.0,
        validation_alias=AliasChoices("GEMINI_TEMPERATURE", "PILOT_GEMINI_TEMPERATURE", "gemini_temperature"),
        description="Gemini temperature",
    )
    gemini_timeout_seconds: int = Field(
        default=30,
        ge=1,
        validation_alias=AliasChoices("GEMINI_TIMEOUT_SECONDS", "PILOT_GEMINI_TIMEOUT_SECONDS", "gemini_timeout_seconds"),
        description="Gemini API timeout in seconds",
    )

    # --- Local LLM Runtime (Ollama) ---
    ollama_base_url: str = Field(
        default="http://127.0.0.1:11434",
        validation_alias=AliasChoices("OLLAMA_BASE_URL", "PILOT_OLLAMA_BASE_URL", "ollama_base_url"),
    )
    ollama_model: str = Field(
        default="qwen2.5:1.5b",
        validation_alias=AliasChoices("OLLAMA_MODEL", "PILOT_OLLAMA_MODEL", "ollama_model"),
    )
    ollama_vision_model: str = Field(
        default="moondream",
        validation_alias=AliasChoices("OLLAMA_VISION_MODEL", "PILOT_OLLAMA_VISION_MODEL", "ollama_vision_model"),
    )
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

    # --- Desktop Automation Config ---
    enable_desktop: bool = True
    desktop_max_elements: int = Field(default=60, ge=10)
    desktop_max_uia_depth: int = Field(default=8, ge=3)
    desktop_observation_timeout_ms: int = Field(default=5000, ge=1000)
    desktop_ui_settle_ms: int = Field(default=500, ge=100)
    desktop_max_iterations: int = Field(default=15, ge=3)




@lru_cache
def get_config() -> PilotConfig:
    """Return the cached application configuration."""

    return PilotConfig()
