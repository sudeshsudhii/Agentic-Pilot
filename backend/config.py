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
    app_version: str = "0.1.0"


@lru_cache
def get_config() -> PilotConfig:
    """Return the cached application configuration."""

    return PilotConfig()
