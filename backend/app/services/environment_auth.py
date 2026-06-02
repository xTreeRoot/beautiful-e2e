from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.project_environments import active_environment_settings

AUTH_HEADER_KEYWORDS = (
    "auth",
    "token",
    "cookie",
    "session",
    "credential",
    "api-key",
    "apikey",
    "jwt",
    "login",
    "satoken",
    "openid",
    "unionid",
    "ticket",
)


def build_environment_auth_context(project_settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """构建给 LLM 使用的环境认证上下文。

    这里只暴露请求头名称，不暴露真实 header 值。生成阶段需要知道哪些认证或网关
    请求头由环境注入，但不应该把用户手动配置的 token 写进 DSL 或提示词。
    """

    environment_settings = active_environment_settings(project_settings)
    request_headers = environment_settings.get("request_headers")
    configured_header_keys = non_empty_header_keys(request_headers)
    likely_auth_header_keys = likely_auth_header_keys_from_headers(request_headers)
    if likely_auth_header_keys:
        mode = "environment_headers"
    elif configured_header_keys:
        mode = "configured_headers"
    else:
        mode = "login_flow_or_unresolved"

    return {
        "mode": mode,
        "active_environment": environment_settings.get("environment"),
        "configured_header_keys": configured_header_keys,
        "likely_auth_header_keys": likely_auth_header_keys,
        "redacted": True,
    }


def build_generation_auth_context(project_settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """兼容旧调用名，实际返回通用环境认证上下文。"""

    return build_environment_auth_context(project_settings)


def non_empty_header_keys(headers: Any) -> list[str]:
    """返回已配置真实值的请求头名称，空值不视为可用认证上下文。"""

    if not isinstance(headers, Mapping):
        return []
    return sorted(
        str(key).strip()
        for key, value in headers.items()
        if str(key).strip() and _has_value(value)
    )


def likely_auth_header_keys_from_headers(headers: Any) -> list[str]:
    """从环境请求头里识别可能承载登录态的 key。

    登录态字段在不同项目里差异很大，因此用关键词匹配，而不是只认识
    `Authorization`。非认证网关头仍会作为 configured_header_keys 暴露给生成器。
    """

    return [key for key in non_empty_header_keys(headers) if _looks_like_auth_header(key)]


def has_non_empty_header(headers: Mapping[str, Any], requested_key: str) -> bool:
    """按大小写不敏感规则判断环境里是否存在同名且有值的请求头。"""

    requested = requested_key.strip().lower()
    if not requested:
        return False
    for key, value in headers.items():
        if str(key).strip().lower() == requested and _has_value(value):
            return True
    return False


def _looks_like_auth_header(key: str) -> bool:
    normalized = key.strip().lower().replace("_", "-")
    return any(keyword in normalized for keyword in AUTH_HEADER_KEYWORDS)


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    return bool(str(value).strip())
