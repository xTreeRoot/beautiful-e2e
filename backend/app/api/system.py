from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import SessionLocal, get_db
from app.schemas import AiProviderUpdate, DirectoryPickOut, DirectoryPickRequest
from app.services.ai import available_provider_descriptors, available_provider_names
from app.services.ai.codex_exec import resolve_codex_executable
from app.services.ai.codex_http_bridge import codex_home, read_auth_api_key, read_provider_base_url
from app.services.ai_settings import (
    CUSTOM_PROVIDER_KEY,
    ai_provider_config_map,
    ai_usage_options,
    ai_usage_plan,
    save_ai_provider_update,
    settings_for_active_ai_provider,
    settings_with_ai_provider,
)

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ai/provider")
def read_ai_provider(db: Session = Depends(get_db)) -> dict[str, Any]:
    return ai_provider(db)


def ai_provider(db: Session | None = None) -> dict[str, Any]:
    if db is None:
        with SessionLocal() as scoped_db:
            return _ai_provider(scoped_db)
    return _ai_provider(db)


def _ai_provider(db: Session) -> dict[str, Any]:
    settings = settings_for_active_ai_provider(get_settings(), db)
    codex_exec_path = resolve_codex_executable(settings.codex_exec_command)
    provider_rows = ai_provider_config_map(db)
    active_provider = CUSTOM_PROVIDER_KEY if settings.ai_provider_entrypoint else settings.ai_provider
    providers = [
        _provider_status(provider, settings, provider_rows.get(str(provider.get("name"))), active_provider)
        for provider in _provider_descriptors(settings, provider_rows)
    ]
    return {
        "provider": settings.ai_provider,
        "active_provider": active_provider,
        "provider_entrypoint": settings.ai_provider_entrypoint,
        "available_providers": available_provider_names(),
        "providers": providers,
        "provider_configured": bool(settings.ai_provider_entrypoint or settings.ai_provider),
        "usage_options": ai_usage_options(),
        "usage_plan": ai_usage_plan(get_settings(), db),
        "bridge_mode": "embedded",
        "bridge_script": str(settings.codex_bridge_script) if settings.codex_bridge_script else None,
        "bridge_script_exists": settings.codex_bridge_script.exists()
        if settings.codex_bridge_script
        else False,
        "model": settings.codex_exec_model or settings.codex_bridge_model or settings.ai_model,
        "wire_api": settings.codex_bridge_wire_api or settings.ai_wire_api,
        "api_key_configured": _api_key_configured(settings),
        "base_url_configured": _base_url_configured(settings),
        "codex_exec_command": settings.codex_exec_command,
        "codex_exec_available": bool(codex_exec_path),
        "codex_exec_path": codex_exec_path,
        "codex_exec_model": settings.codex_exec_model,
        "codex_exec_profile": settings.codex_exec_profile,
        "codex_exec_profile_v2": settings.codex_exec_profile_v2,
        "codex_exec_cwd": str(settings.codex_exec_cwd) if settings.codex_exec_cwd else None,
        "codex_exec_sandbox": settings.codex_exec_sandbox,
        "codex_exec_ephemeral": settings.codex_exec_ephemeral,
        "codex_exec_skip_git_repo_check": settings.codex_exec_skip_git_repo_check,
        "codex_exec_ignore_user_config": settings.codex_exec_ignore_user_config,
        "codex_exec_ignore_rules": settings.codex_exec_ignore_rules,
        "codex_exec_strict_config": settings.codex_exec_strict_config,
        "codex_exec_output_schema_enabled": settings.codex_exec_output_schema_enabled,
        "codex_exec_oss": settings.codex_exec_oss,
        "codex_exec_local_provider": settings.codex_exec_local_provider,
        "codex_exec_image_paths": settings.codex_exec_image_paths,
        "codex_exec_add_dirs": settings.codex_exec_add_dirs,
        "codex_exec_config_overrides": settings.codex_exec_config_overrides,
        "codex_exec_enabled_features": settings.codex_exec_enabled_features,
        "codex_exec_disabled_features": settings.codex_exec_disabled_features,
        "codex_exec_dangerously_bypass_approvals_and_sandbox": (
            settings.codex_exec_dangerously_bypass_approvals_and_sandbox
        ),
        "codex_exec_dangerously_bypass_hook_trust": (
            settings.codex_exec_dangerously_bypass_hook_trust
        ),
        "codex_exec_capabilities": _codex_exec_capabilities(),
        "fallback_rule_based": settings.ai_fallback_rule_based,
    }


@router.put("/ai/provider")
def write_ai_provider(
    payload: AiProviderUpdate,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return update_ai_provider(payload, db)


def update_ai_provider(payload: AiProviderUpdate, db: Session | None = None) -> dict[str, Any]:
    if db is None:
        with SessionLocal() as scoped_db:
            return _update_ai_provider(payload, scoped_db)
    return _update_ai_provider(payload, db)


def _update_ai_provider(payload: AiProviderUpdate, db: Session) -> dict[str, Any]:
    if (
        payload.provider
        and payload.provider != CUSTOM_PROVIDER_KEY
        and payload.provider not in available_provider_names()
    ):
        raise HTTPException(status_code=400, detail=f"未知 AI 供应商：{payload.provider}")
    _set_env("AI_PROVIDER", payload.provider)
    _set_env("AI_PROVIDER_ENTRYPOINT", payload.provider_entrypoint)
    _set_env("AI_API_KEY", payload.api_key)
    _set_env("AI_BASE_URL", payload.base_url)
    _set_env("AI_MODEL", payload.model)
    _set_env("AI_WIRE_API", payload.wire_api)
    _set_env("AI_REASONING_EFFORT", payload.reasoning_effort)
    _set_env("AI_TIMEOUT_SECONDS", str(payload.timeout_seconds) if payload.timeout_seconds else None)
    _set_env("CODEX_EXEC_COMMAND", payload.codex_exec_command)
    _set_env("CODEX_EXEC_MODEL", payload.codex_exec_model)
    _set_env("CODEX_EXEC_PROFILE", payload.codex_exec_profile)
    _set_env("CODEX_EXEC_PROFILE_V2", payload.codex_exec_profile_v2)
    _set_env("CODEX_EXEC_CWD", payload.codex_exec_cwd)
    _set_env("CODEX_EXEC_SANDBOX", payload.codex_exec_sandbox)
    _set_env_bool("CODEX_EXEC_EPHEMERAL", payload.codex_exec_ephemeral)
    _set_env_bool("CODEX_EXEC_SKIP_GIT_REPO_CHECK", payload.codex_exec_skip_git_repo_check)
    _set_env_bool("CODEX_EXEC_IGNORE_USER_CONFIG", payload.codex_exec_ignore_user_config)
    _set_env_bool("CODEX_EXEC_IGNORE_RULES", payload.codex_exec_ignore_rules)
    _set_env_bool("CODEX_EXEC_STRICT_CONFIG", payload.codex_exec_strict_config)
    _set_env_bool("CODEX_EXEC_OUTPUT_SCHEMA_ENABLED", payload.codex_exec_output_schema_enabled)
    _set_env_bool("CODEX_EXEC_OSS", payload.codex_exec_oss)
    _set_env("CODEX_EXEC_LOCAL_PROVIDER", payload.codex_exec_local_provider)
    _set_env_list("CODEX_EXEC_IMAGE_PATHS", payload.codex_exec_image_paths)
    _set_env_list("CODEX_EXEC_ADD_DIRS", payload.codex_exec_add_dirs)
    _set_env_list("CODEX_EXEC_CONFIG_OVERRIDES", payload.codex_exec_config_overrides)
    _set_env_list("CODEX_EXEC_ENABLED_FEATURES", payload.codex_exec_enabled_features)
    _set_env_list("CODEX_EXEC_DISABLED_FEATURES", payload.codex_exec_disabled_features)
    _set_env_bool(
        "CODEX_EXEC_DANGEROUSLY_BYPASS_APPROVALS_AND_SANDBOX",
        payload.codex_exec_dangerously_bypass_approvals_and_sandbox,
    )
    _set_env_bool(
        "CODEX_EXEC_DANGEROUSLY_BYPASS_HOOK_TRUST",
        payload.codex_exec_dangerously_bypass_hook_trust,
    )
    get_settings.cache_clear()
    try:
        save_ai_provider_update(get_settings(), db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return _ai_provider(db)


@router.post("/fs/pick-directory", response_model=DirectoryPickOut)
def pick_directory(payload: DirectoryPickRequest) -> DirectoryPickOut:
    path = _pick_directory(payload.title, payload.initial_path)
    return DirectoryPickOut(path=path, canceled=path is None)


def _pick_directory(title: str, initial_path: str | None) -> str | None:
    if sys.platform == "darwin":
        return _pick_directory_macos(title, initial_path)
    return _pick_directory_tk(title, initial_path)


def _pick_directory_macos(title: str, initial_path: str | None) -> str | None:
    prompt = _escape_applescript_text(title or "选择目录")
    initial = _existing_directory(initial_path)
    if initial:
        default_location = _escape_applescript_text(str(initial))
        script = (
            f'set defaultPath to POSIX file "{default_location}"\n'
            f'set chosenFolder to choose folder with prompt "{prompt}" default location defaultPath\n'
            "POSIX path of chosenFolder"
        )
    else:
        script = f'set chosenFolder to choose folder with prompt "{prompt}"\nPOSIX path of chosenFolder'

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(status_code=500, detail=f"无法打开目录选择框: {exc}") from exc

    if result.returncode != 0:
        if "User canceled" in result.stderr:
            return None
        raise HTTPException(status_code=500, detail=result.stderr.strip() or "目录选择失败")

    selected = result.stdout.strip()
    return selected.rstrip("/") if selected else None


def _pick_directory_tk(title: str, initial_path: str | None) -> str | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"当前环境不支持目录选择框: {exc}") from exc

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    initial = _existing_directory(initial_path)
    selected = filedialog.askdirectory(title=title or "选择目录", initialdir=str(initial) if initial else None)
    root.destroy()
    return selected or None


def _existing_directory(raw_path: str | None) -> Path | None:
    if not raw_path:
        return None
    path = Path(raw_path).expanduser()
    if path.is_file():
        return path.parent
    return path if path.exists() and path.is_dir() else None


def _escape_applescript_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _provider_descriptors(settings: Any, provider_rows: dict[str, Any]) -> list[dict[str, Any]]:
    descriptors = available_provider_descriptors(settings)
    has_custom = any(item.get("name") == CUSTOM_PROVIDER_KEY for item in descriptors)
    custom_row = provider_rows.get(CUSTOM_PROVIDER_KEY)
    if custom_row is not None and not has_custom:
        descriptors.append(
            {
                "name": CUSTOM_PROVIDER_KEY,
                "label": "自定义 Python 供应商",
                "description": "通过 AI_PROVIDER_ENTRYPOINT 注入团队内部供应商工厂。",
                "mode": "custom",
                "protocol": "python_entrypoint",
                "configurable": True,
                "env_vars": ["AI_PROVIDER_ENTRYPOINT"],
                "entrypoint": custom_row.provider_entrypoint,
            }
        )
    return sorted(descriptors, key=lambda item: str(item["name"]))


def _provider_status(
    provider: dict[str, Any],
    settings: Any,
    row: Any,
    active_provider: str,
) -> dict[str, Any]:
    name = str(provider.get("name"))
    provider_settings = (
        settings_with_ai_provider(settings, _row_resolved_provider(name, row))
        if row is not None
        else settings
    )
    result = {
        **provider,
        "active": name == active_provider,
        "available": True,
        "configured": False,
        "usages": row.usage_keys if row is not None and isinstance(row.usage_keys, list) else [],
    }
    if name == "codex_exec":
        resolved = resolve_codex_executable(provider_settings.codex_exec_command)
        result["available"] = bool(resolved)
        result["configured"] = result["available"]
        result["resolved_command"] = resolved
    elif name == "rule_based":
        result["configured"] = True
    elif name == "codex_bridge":
        result["configured"] = _api_key_configured(provider_settings) and _base_url_configured(
            provider_settings
        )
    elif name == "openai_compatible":
        result["configured"] = bool(provider_settings.ai_api_key and provider_settings.ai_base_url)
    elif name == CUSTOM_PROVIDER_KEY:
        result["configured"] = bool(provider_settings.ai_provider_entrypoint)
    return result


def _codex_exec_capabilities() -> dict[str, Any]:
    """把当前系统支持的 `codex exec` 能力返回给前端配置面板。"""
    return {
        "streaming": {
            "json_events": True,
            "reasoning_delta": "cli_exposed_only",
            "final_message_file": True,
        },
        "sandbox_modes": ["inherit", "read-only", "workspace-write", "danger-full-access"],
        "local_providers": ["inherit", "lmstudio", "ollama"],
        "flags": [
            "config",
            "enable",
            "disable",
            "strict_config",
            "image",
            "model",
            "oss",
            "local_provider",
            "profile",
            "profile_v2",
            "sandbox",
            "dangerously_bypass_approvals_and_sandbox",
            "dangerously_bypass_hook_trust",
            "cd",
            "add_dir",
            "skip_git_repo_check",
            "ephemeral",
            "ignore_user_config",
            "ignore_rules",
            "output_schema",
            "json",
            "output_last_message",
        ],
    }


def _row_resolved_provider(name: str, row: Any) -> Any:
    from app.services.ai_settings import ResolvedAiProvider

    config = dict(row.config or {})
    return ResolvedAiProvider(
        provider_key=name,
        provider_entrypoint=row.provider_entrypoint or config.get("provider_entrypoint"),
        config=config,
        row=row,
    )


def _api_key_configured(settings: Any) -> bool:
    home = codex_home(settings.ai_codex_home)
    return bool(settings.ai_api_key or os.getenv("OPENAI_API_KEY") or read_auth_api_key(home))


def _base_url_configured(settings: Any) -> bool:
    home = codex_home(settings.ai_codex_home)
    return bool(settings.ai_base_url or os.getenv("OPENAI_BASE_URL") or read_provider_base_url(home))


def _set_env(name: str, value: str | None) -> None:
    if value is None:
        return
    normalized = value.strip()
    if normalized:
        os.environ[name] = normalized
    else:
        os.environ.pop(name, None)


def _set_env_bool(name: str, value: bool | None) -> None:
    if value is None:
        return
    os.environ[name] = "true" if value else "false"


def _set_env_list(name: str, value: list[str] | None) -> None:
    if value is None:
        return
    normalized = [item.strip() for item in value if item.strip()]
    if normalized:
        os.environ[name] = json.dumps(normalized, ensure_ascii=False)
    else:
        os.environ.pop(name, None)
