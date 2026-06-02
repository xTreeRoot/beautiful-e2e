from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Beautiful E2E"
    database_url: str = (
        "mysql+pymysql://beautiful_e2e:beautiful_e2e@127.0.0.1:3306/"
        "beautiful_e2e?charset=utf8mb4"
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    workspace_scan_max_files: int = 160
    generated_specs_dir: Path = Path("../runner/tests/generated")
    ai_provider: str = "codex_exec"
    ai_provider_entrypoint: str | None = None
    ai_provider_config: dict[str, Any] = Field(default_factory=dict)
    ai_fallback_rule_based: bool = True
    ai_api_key: str | None = None
    ai_base_url: str | None = None
    ai_model: str = "gpt-5.5"
    ai_wire_api: str = "responses"
    ai_reasoning_effort: str = "xhigh"
    ai_timeout_seconds: int = 180
    ai_max_tokens: int = 3000
    ai_codex_home: Path | None = None
    codex_bridge_script: Path | None = None
    codex_bridge_model: str | None = None
    codex_bridge_wire_api: str | None = None
    codex_bridge_reasoning_effort: str | None = None
    codex_bridge_timeout_seconds: int | None = None
    codex_exec_command: str = "codex"
    codex_exec_model: str | None = None
    codex_exec_profile: str | None = None
    codex_exec_profile_v2: str | None = None
    codex_exec_cwd: Path | None = None
    codex_exec_sandbox: str | None = None
    codex_exec_ephemeral: bool = False
    codex_exec_skip_git_repo_check: bool = False
    codex_exec_ignore_user_config: bool = False
    codex_exec_ignore_rules: bool = False
    codex_exec_strict_config: bool = False
    codex_exec_output_schema_enabled: bool = True
    codex_exec_oss: bool = False
    codex_exec_local_provider: str | None = None
    codex_exec_image_paths: list[str] = Field(default_factory=list)
    codex_exec_add_dirs: list[str] = Field(default_factory=list)
    codex_exec_config_overrides: list[str] = Field(default_factory=list)
    codex_exec_enabled_features: list[str] = Field(default_factory=list)
    codex_exec_disabled_features: list[str] = Field(default_factory=list)
    codex_exec_dangerously_bypass_approvals_and_sandbox: bool = False
    codex_exec_dangerously_bypass_hook_trust: bool = False
    codex_exec_timeout_seconds: int | None = 300
    api_runtime_ai_inference_enabled: bool = True
    api_runtime_ai_inference_min_confidence: float = 0.65
    api_runtime_ai_inference_timeout_seconds: int = 45

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
