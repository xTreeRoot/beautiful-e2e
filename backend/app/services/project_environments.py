from __future__ import annotations

from collections.abc import Mapping
from typing import Any

DEFAULT_ENVIRONMENT = "local"
DEFAULT_FRONTEND_BASE_URL = "http://localhost:5173"
DEFAULT_API_BASE_URL = "http://localhost:8000"


def active_environment_settings(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """把当前项目环境解析为 Playwright 使用的默认地址。

    项目设置保留兼容旧数据的顶层 `base_url` 与 `api_base_url`，新工作区
    可以按环境保存多行地址。导出时优先使用已选择的环境，再回退到旧字段，
    保证旧本地数据库仍可工作。
    """

    settings = settings or {}
    legacy_environment = _clean_string(settings.get("active_environment")) or DEFAULT_ENVIRONMENT
    frontend_environment = (
        _clean_string(settings.get("active_frontend_environment")) or legacy_environment
    )
    api_environment = (
        _clean_string(settings.get("active_api_environment"))
        or _clean_string(settings.get("active_backend_environment"))
        or legacy_environment
    )
    base_url = _clean_string(settings.get("base_url")) or DEFAULT_FRONTEND_BASE_URL
    api_base_url = _clean_string(settings.get("api_base_url")) or DEFAULT_API_BASE_URL
    request_headers: Any = settings.get("request_headers") or {}

    environments = settings.get("environments")
    if isinstance(environments, list):
        for raw_environment in environments:
            if not isinstance(raw_environment, Mapping):
                continue
            key = (
                _clean_string(raw_environment.get("key"))
                or _clean_string(raw_environment.get("id"))
                or _clean_string(raw_environment.get("name"))
            )
            if key == frontend_environment:
                base_url = (
                    _clean_string(raw_environment.get("base_url"))
                    or _clean_string(raw_environment.get("baseUrl"))
                    or base_url
                )
            if key == api_environment:
                api_base_url = (
                    _clean_string(raw_environment.get("api_base_url"))
                    or _clean_string(raw_environment.get("apiBaseUrl"))
                    or api_base_url
                )
                request_headers = (
                    raw_environment.get("request_headers")
                    if raw_environment.get("request_headers") is not None
                    else raw_environment.get("headers", request_headers)
                )

    return {
        "environment": (
            frontend_environment
            if frontend_environment == api_environment
            else f"{frontend_environment}/{api_environment}"
        ),
        "base_url": base_url,
        "api_base_url": api_base_url,
        "request_headers": request_headers if isinstance(request_headers, dict) else {},
    }


def _clean_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None
