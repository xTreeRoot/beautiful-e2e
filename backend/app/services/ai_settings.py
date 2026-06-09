from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import AiProviderConfig
from app.schemas import AiProviderUpdate
from app.services.ai import available_provider_names

AI_USAGE_PROJECT_ANALYSIS = "project_analysis"
AI_USAGE_DSL_GENERATION = "dsl_generation"
AI_USAGE_API_RUNTIME = "api_runtime"


@dataclass(frozen=True)
class AiUsageOption:
    key: str
    label: str
    description: str

    def as_dict(self) -> dict[str, str]:
        return {"key": self.key, "label": self.label, "description": self.description}


@dataclass(frozen=True)
class ResolvedAiProvider:
    provider_key: str
    provider_entrypoint: str | None
    config: dict[str, Any]
    row: AiProviderConfig | None = None


AI_USAGE_OPTIONS: tuple[AiUsageOption, ...] = (
    AiUsageOption(
        key=AI_USAGE_PROJECT_ANALYSIS,
        label="项目分析",
        description="读取仓库结构、路由和页面线索时使用的 AI。",
    ),
    AiUsageOption(
        key=AI_USAGE_DSL_GENERATION,
        label="Prompt 生成 DSL",
        description="把自然语言需求生成用例图和步骤 DSL 时使用的 AI。",
    ),
    AiUsageOption(
        key=AI_USAGE_API_RUNTIME,
        label="接口运行辅助测试",
        description="接口运行时推导缺失变量和响应字段时使用的 AI。",
    ),
)
VALID_AI_USAGE_KEYS = {option.key for option in AI_USAGE_OPTIONS}
CUSTOM_PROVIDER_KEY = "custom_entrypoint"


def ai_usage_options() -> list[dict[str, str]]:
    return [option.as_dict() for option in AI_USAGE_OPTIONS]


def ai_provider_config_rows(db: Session) -> list[AiProviderConfig]:
    return list(db.scalars(select(AiProviderConfig).order_by(AiProviderConfig.provider_key)))


def ai_provider_config_map(db: Session) -> dict[str, AiProviderConfig]:
    return {row.provider_key: row for row in ai_provider_config_rows(db)}


def active_ai_provider_key(settings: Settings, db: Session) -> str:
    row = db.scalar(select(AiProviderConfig).where(AiProviderConfig.is_active.is_(True)))
    if row is not None and _is_known_provider(row.provider_key):
        return row.provider_key
    return _settings_provider_key(settings)


def ai_usage_plan(settings: Settings, db: Session) -> dict[str, str]:
    """返回完整用途规划，未落库的用途继承当前默认供应商。

    这样旧数据库或首次启动时仍保持原来的单供应商行为；一旦用户保存，
    规划就会写入 `ai_provider_configs.usage_keys`。
    """

    plan: dict[str, str] = {}
    for row in ai_provider_config_rows(db):
        if not _is_known_provider(row.provider_key):
            continue
        for usage_key in _normalized_usage_keys(row.usage_keys):
            plan.setdefault(usage_key, row.provider_key)

    fallback = active_ai_provider_key(settings, db)
    for option in AI_USAGE_OPTIONS:
        plan.setdefault(option.key, fallback)
    return plan


def settings_for_ai_usage(settings: Settings, db: Session, usage_key: str) -> Settings:
    """按业务用途生成有效 Settings，避免全局 AI 配置在多个流程间互相覆盖。"""

    resolved = resolve_ai_provider_for_usage(settings, db, usage_key)
    return settings_with_ai_provider(settings, resolved)


def settings_for_active_ai_provider(settings: Settings, db: Session) -> Settings:
    active_key = active_ai_provider_key(settings, db)
    row = ai_provider_config_map(db).get(active_key)
    resolved = _resolved_from_row(row) if row else _resolved_from_settings(settings, active_key)
    return settings_with_ai_provider(settings, resolved)


def resolve_ai_provider_for_usage(
    settings: Settings,
    db: Session,
    usage_key: str,
) -> ResolvedAiProvider:
    if usage_key not in VALID_AI_USAGE_KEYS:
        return _resolved_from_settings(settings, active_ai_provider_key(settings, db))

    plan = ai_usage_plan(settings, db)
    provider_key = plan.get(usage_key) or active_ai_provider_key(settings, db)
    row = ai_provider_config_map(db).get(provider_key)
    if row is not None:
        return _resolved_from_row(row)
    return _resolved_from_settings(settings, provider_key)


def settings_with_ai_provider(settings: Settings, resolved: ResolvedAiProvider) -> Settings:
    config = dict(resolved.config)
    provider_key = resolved.provider_key
    update: dict[str, Any] = {"ai_provider_config": config}

    if provider_key == CUSTOM_PROVIDER_KEY:
        update["ai_provider"] = ""
        update["ai_provider_entrypoint"] = resolved.provider_entrypoint
    else:
        update["ai_provider"] = provider_key
        update["ai_provider_entrypoint"] = None

    # 这些字段既供旧逻辑读取，也让状态接口能按落库配置计算可用性。
    if "api_key" in config:
        update["ai_api_key"] = _clean_optional(config.get("api_key"))
    if "base_url" in config:
        update["ai_base_url"] = _clean_optional(config.get("base_url"))
    if "model" in config:
        update["ai_model"] = str(config.get("model") or settings.ai_model)
        update["codex_bridge_model"] = _clean_optional(config.get("model"))
        update["codex_exec_model"] = _clean_optional(config.get("model"))
    if "wire_api" in config:
        update["ai_wire_api"] = str(config.get("wire_api") or settings.ai_wire_api)
        update["codex_bridge_wire_api"] = _clean_optional(config.get("wire_api"))
    if "reasoning_effort" in config:
        update["ai_reasoning_effort"] = str(
            config.get("reasoning_effort") or settings.ai_reasoning_effort
        )
        update["codex_bridge_reasoning_effort"] = _clean_optional(config.get("reasoning_effort"))
    if "timeout_seconds" in config:
        update["ai_timeout_seconds"] = int(config.get("timeout_seconds") or settings.ai_timeout_seconds)
    if "executable" in config:
        update["codex_exec_command"] = str(config.get("executable") or settings.codex_exec_command)
    if "profile" in config:
        update["codex_exec_profile"] = _clean_optional(config.get("profile"))
    if "profile_v2" in config:
        update["codex_exec_profile_v2"] = _clean_optional(config.get("profile_v2"))
    if "cwd" in config:
        update["codex_exec_cwd"] = _clean_optional(config.get("cwd"))
    if "sandbox" in config:
        update["codex_exec_sandbox"] = _clean_optional(config.get("sandbox"))
    for key in (
        "ephemeral",
        "skip_git_repo_check",
        "ignore_user_config",
        "ignore_rules",
        "strict_config",
        "output_schema_enabled",
        "oss",
        "dangerously_bypass_approvals_and_sandbox",
        "dangerously_bypass_hook_trust",
    ):
        if key in config:
            update[f"codex_exec_{key}"] = _bool_config(config.get(key))
    if "local_provider" in config:
        update["codex_exec_local_provider"] = _clean_optional(config.get("local_provider"))
    for key in (
        "image_paths",
        "add_dirs",
        "config_overrides",
        "enabled_features",
        "disabled_features",
    ):
        if key in config:
            update[f"codex_exec_{key}"] = _string_list(config.get(key))

    return settings.model_copy(update=update)


def save_ai_provider_update(settings: Settings, db: Session, payload: AiProviderUpdate) -> None:
    previous_provider_key = active_ai_provider_key(settings, db)
    previous_usage_plan = ai_usage_plan(settings, db)
    provider_key = _payload_provider_key(payload, settings, db)
    _validate_provider_key(provider_key)
    row = _get_or_create_provider_config(db, provider_key)

    if provider_key == CUSTOM_PROVIDER_KEY:
        row.provider_entrypoint = _clean_optional(payload.provider_entrypoint) or row.provider_entrypoint
    else:
        row.provider_entrypoint = None

    row.config = _merged_provider_config(provider_key, row.config, payload)
    _mark_active_provider(db, row)

    usage_plan = _usage_plan_for_provider_switch(
        payload.usage_plan,
        previous_usage_plan,
        previous_provider_key=previous_provider_key,
        provider_key=provider_key,
    )
    if usage_plan is not None:
        _save_usage_plan(settings, db, usage_plan, fallback_provider_key=provider_key)


def _save_usage_plan(
    settings: Settings,
    db: Session,
    raw_plan: Mapping[str, str],
    *,
    fallback_provider_key: str,
) -> None:
    current_plan = ai_usage_plan(settings, db)
    normalized_plan: dict[str, str] = {}

    for option in AI_USAGE_OPTIONS:
        provider_key = (
            _clean_optional(raw_plan.get(option.key))
            or current_plan.get(option.key)
            or fallback_provider_key
        )
        _validate_provider_key(provider_key)
        normalized_plan[option.key] = provider_key
        _get_or_create_provider_config(db, provider_key)

    for row in ai_provider_config_rows(db):
        row.usage_keys = []

    rows = ai_provider_config_map(db)
    for usage_key, provider_key in normalized_plan.items():
        row = rows[provider_key]
        row.usage_keys = [*(_normalized_usage_keys(row.usage_keys)), usage_key]


def _usage_plan_for_provider_switch(
    raw_plan: Mapping[str, str] | None,
    current_plan: Mapping[str, str],
    *,
    previous_provider_key: str,
    provider_key: str,
) -> dict[str, str] | None:
    """主供应商切换时，让沿用旧主供应商的用途自然跟随新主供应商。

    前端旧表单会把保存前的用途规划原样带回；如果不识别这个场景，用户点击
    `codex_exec` 后，Prompt 生成 DSL 仍可能继续使用旧供应商。
    """

    if raw_plan is None and previous_provider_key == provider_key:
        return None

    next_plan = {
        option.key: _clean_optional((raw_plan or {}).get(option.key))
        or current_plan.get(option.key)
        or provider_key
        for option in AI_USAGE_OPTIONS
    }
    if previous_provider_key == provider_key:
        return next_plan
    if raw_plan is not None and not _raw_usage_plan_matches_current(raw_plan, current_plan):
        return next_plan

    return {
        usage_key: provider_key if assigned_provider == previous_provider_key else assigned_provider
        for usage_key, assigned_provider in next_plan.items()
    }


def _raw_usage_plan_matches_current(
    raw_plan: Mapping[str, str],
    current_plan: Mapping[str, str],
) -> bool:
    for option in AI_USAGE_OPTIONS:
        provider_key = _clean_optional(raw_plan.get(option.key))
        if provider_key is not None and provider_key != current_plan.get(option.key):
            return False
    return True


def _payload_provider_key(payload: AiProviderUpdate, settings: Settings, db: Session) -> str:
    if _clean_optional(payload.provider_entrypoint) and not _clean_optional(payload.provider):
        return CUSTOM_PROVIDER_KEY
    if _clean_optional(payload.provider) == CUSTOM_PROVIDER_KEY:
        return CUSTOM_PROVIDER_KEY
    return (
        _clean_optional(payload.provider)
        or active_ai_provider_key(settings, db)
        or _settings_provider_key(settings)
    )


def _mark_active_provider(db: Session, active_row: AiProviderConfig) -> None:
    for row in ai_provider_config_rows(db):
        row.is_active = row.id == active_row.id
    active_row.is_active = True


def _get_or_create_provider_config(db: Session, provider_key: str) -> AiProviderConfig:
    row = db.scalar(select(AiProviderConfig).where(AiProviderConfig.provider_key == provider_key))
    if row is None:
        row = AiProviderConfig(provider_key=provider_key, config={}, usage_keys=[])
        db.add(row)
        db.flush()
    return row


def _merged_provider_config(
    provider_key: str,
    current: Mapping[str, Any] | None,
    payload: AiProviderUpdate,
) -> dict[str, Any]:
    config = {key: value for key, value in dict(current or {}).items() if value not in (None, "")}

    if provider_key == "codex_exec":
        _assign_clean(config, "executable", payload.codex_exec_command)
        _assign_clean(config, "model", payload.codex_exec_model)
        _assign_clean(config, "profile", payload.codex_exec_profile)
        _assign_clean(config, "profile_v2", payload.codex_exec_profile_v2)
        _assign_clean(config, "cwd", payload.codex_exec_cwd)
        _assign_clean(config, "sandbox", payload.codex_exec_sandbox)
        _assign_bool(config, "ephemeral", payload.codex_exec_ephemeral)
        _assign_bool(config, "skip_git_repo_check", payload.codex_exec_skip_git_repo_check)
        _assign_bool(config, "ignore_user_config", payload.codex_exec_ignore_user_config)
        _assign_bool(config, "ignore_rules", payload.codex_exec_ignore_rules)
        _assign_bool(config, "strict_config", payload.codex_exec_strict_config)
        _assign_bool(config, "output_schema_enabled", payload.codex_exec_output_schema_enabled)
        _assign_bool(config, "oss", payload.codex_exec_oss)
        _assign_clean(config, "local_provider", payload.codex_exec_local_provider)
        _assign_string_list(config, "image_paths", payload.codex_exec_image_paths)
        _assign_string_list(config, "add_dirs", payload.codex_exec_add_dirs)
        _assign_string_list(config, "config_overrides", payload.codex_exec_config_overrides)
        _assign_string_list(config, "enabled_features", payload.codex_exec_enabled_features)
        _assign_string_list(config, "disabled_features", payload.codex_exec_disabled_features)
        _assign_bool(
            config,
            "dangerously_bypass_approvals_and_sandbox",
            payload.codex_exec_dangerously_bypass_approvals_and_sandbox,
        )
        _assign_bool(
            config,
            "dangerously_bypass_hook_trust",
            payload.codex_exec_dangerously_bypass_hook_trust,
        )
        if payload.timeout_seconds is not None:
            config["timeout_seconds"] = payload.timeout_seconds
        return config

    if provider_key in {"codex_bridge", "openai_compatible"}:
        _assign_clean(config, "api_key", payload.api_key)
        _assign_clean(config, "base_url", payload.base_url)
        _assign_clean(config, "model", payload.model)
        _assign_clean(config, "wire_api", payload.wire_api)
        _assign_clean(config, "reasoning_effort", payload.reasoning_effort)
        if payload.timeout_seconds is not None:
            config["timeout_seconds"] = payload.timeout_seconds
        return config

    if provider_key == CUSTOM_PROVIDER_KEY:
        _assign_clean(config, "provider_entrypoint", payload.provider_entrypoint)
    return config


def _resolved_from_row(row: AiProviderConfig) -> ResolvedAiProvider:
    config = dict(row.config or {})
    entrypoint = row.provider_entrypoint or _clean_optional(config.get("provider_entrypoint"))
    return ResolvedAiProvider(
        provider_key=row.provider_key,
        provider_entrypoint=entrypoint,
        config=config,
        row=row,
    )


def _resolved_from_settings(settings: Settings, provider_key: str | None = None) -> ResolvedAiProvider:
    key = provider_key or _settings_provider_key(settings)
    return ResolvedAiProvider(
        provider_key=key,
        provider_entrypoint=settings.ai_provider_entrypoint if key == CUSTOM_PROVIDER_KEY else None,
        config=_settings_provider_config(settings, key),
    )


def _settings_provider_key(settings: Settings) -> str:
    if settings.ai_provider_entrypoint:
        return CUSTOM_PROVIDER_KEY
    return settings.ai_provider.strip() or "codex_exec"


def _settings_provider_config(settings: Settings, provider_key: str) -> dict[str, Any]:
    config = dict(settings.ai_provider_config or {})
    if provider_key == "codex_exec":
        config.setdefault("executable", settings.codex_exec_command)
        _set_if_present(config, "model", settings.codex_exec_model)
        _set_if_present(config, "profile", settings.codex_exec_profile)
        _set_if_present(config, "profile_v2", settings.codex_exec_profile_v2)
        _set_if_present(config, "cwd", str(settings.codex_exec_cwd) if settings.codex_exec_cwd else None)
        _set_if_present(config, "sandbox", settings.codex_exec_sandbox)
        _set_bool_if_true(config, "ephemeral", settings.codex_exec_ephemeral)
        _set_bool_if_true(config, "skip_git_repo_check", settings.codex_exec_skip_git_repo_check)
        _set_bool_if_true(config, "ignore_user_config", settings.codex_exec_ignore_user_config)
        _set_bool_if_true(config, "ignore_rules", settings.codex_exec_ignore_rules)
        _set_bool_if_true(config, "strict_config", settings.codex_exec_strict_config)
        if settings.codex_exec_output_schema_enabled is False:
            config.setdefault("output_schema_enabled", False)
        _set_bool_if_true(config, "oss", settings.codex_exec_oss)
        _set_if_present(config, "local_provider", settings.codex_exec_local_provider)
        _set_list_if_present(config, "image_paths", settings.codex_exec_image_paths)
        _set_list_if_present(config, "add_dirs", settings.codex_exec_add_dirs)
        _set_list_if_present(config, "config_overrides", settings.codex_exec_config_overrides)
        _set_list_if_present(config, "enabled_features", settings.codex_exec_enabled_features)
        _set_list_if_present(config, "disabled_features", settings.codex_exec_disabled_features)
        _set_bool_if_true(
            config,
            "dangerously_bypass_approvals_and_sandbox",
            settings.codex_exec_dangerously_bypass_approvals_and_sandbox,
        )
        _set_bool_if_true(
            config,
            "dangerously_bypass_hook_trust",
            settings.codex_exec_dangerously_bypass_hook_trust,
        )
    elif provider_key in {"codex_bridge", "openai_compatible"}:
        _set_if_present(config, "api_key", settings.ai_api_key)
        _set_if_present(config, "base_url", settings.ai_base_url)
        _set_if_present(
            config,
            "model",
            settings.codex_bridge_model if provider_key == "codex_bridge" else settings.ai_model,
        )
        _set_if_present(
            config,
            "wire_api",
            settings.codex_bridge_wire_api if provider_key == "codex_bridge" else settings.ai_wire_api,
        )
        _set_if_present(config, "reasoning_effort", settings.ai_reasoning_effort)
    elif provider_key == CUSTOM_PROVIDER_KEY:
        _set_if_present(config, "provider_entrypoint", settings.ai_provider_entrypoint)
    return config


def _normalized_usage_keys(raw_keys: Any) -> list[str]:
    if not isinstance(raw_keys, list):
        return []
    normalized: list[str] = []
    for item in raw_keys:
        usage_key = str(item)
        if usage_key in VALID_AI_USAGE_KEYS and usage_key not in normalized:
            normalized.append(usage_key)
    return normalized


def _validate_provider_key(provider_key: str) -> None:
    if not _is_known_provider(provider_key):
        raise ValueError(f"未知 AI 供应商：{provider_key}")


def _is_known_provider(provider_key: str) -> bool:
    return provider_key == CUSTOM_PROVIDER_KEY or provider_key in available_provider_names()


def _assign_clean(config: dict[str, Any], key: str, value: Any) -> None:
    normalized = _clean_optional(value)
    if normalized is not None:
        config[key] = normalized


def _assign_bool(config: dict[str, Any], key: str, value: bool | None) -> None:
    if value is not None:
        config[key] = bool(value)


def _assign_string_list(config: dict[str, Any], key: str, value: list[str] | None) -> None:
    if value is None:
        return
    normalized = [item.strip() for item in value if item.strip()]
    if normalized:
        config[key] = normalized
    else:
        config.pop(key, None)


def _set_if_present(config: dict[str, Any], key: str, value: Any) -> None:
    if value not in (None, ""):
        config.setdefault(key, value)


def _set_bool_if_true(config: dict[str, Any], key: str, value: bool) -> None:
    if value:
        config.setdefault(key, True)


def _set_list_if_present(config: dict[str, Any], key: str, value: list[str]) -> None:
    normalized = [item.strip() for item in value if item.strip()]
    if normalized:
        config.setdefault(key, normalized)


def _bool_config(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value in (None, ""):
        return []
    return [item.strip() for item in str(value).replace("\n", ",").split(",") if item.strip()]


def _clean_optional(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
