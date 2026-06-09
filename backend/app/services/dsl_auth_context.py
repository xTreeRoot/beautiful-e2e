from __future__ import annotations

from copy import deepcopy
from typing import Any

DSL_AUTH_MODE = "project_request_headers"

_AUTH_RULE_MARKERS = (
    "auth.effective_mode",
    "认证",
    "登录",
    "登陆",
    "登录态",
    "请求头",
    "header",
    "token",
    "cookie",
    "session",
)

_DSL_AUTH_RULES = [
    "生成 DSL 时认证、登录态、Cookie、session、token 和网关请求头统一由项目请求头注入。",
    "不要为登录态生成登录/登出步骤、认证接口、token extract、cookie/session extract 或认证 header 占位符。",
    "项目请求头只暴露 key，不暴露真实值；真实值由用户在项目环境里维护，运行时自动合并。",
    "业务实体 ID、业务编号、状态型业务 ID 等业务变量仍必须来自前置业务接口响应或显式测试夹具。",
]


def build_dsl_project_context(
    project_context: dict[str, Any] | None,
    auth_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构建专供 DSL 生成模型使用的项目上下文。

    项目分析仍会保存登录接口候选，供分析页和人工排查使用；但 DSL 生成阶段
    不应把这些候选暴露成可采用方案，否则模型容易把认证链路写进测试步骤。
    """

    context = (
        deepcopy(project_context)
        if isinstance(project_context, dict)
        else _default_project_context()
    )
    context["auth"] = build_dsl_auth_context(context, auth_context)
    context["rules"] = _dsl_rules(context.get("rules"))
    repositories = context.get("repositories")
    if isinstance(repositories, list):
        context["repositories"] = [
            _sanitize_repository(repository)
            for repository in repositories
            if isinstance(repository, dict)
        ]
    return context


def build_dsl_auth_context(
    project_context: dict[str, Any] | None,
    auth_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """返回 DSL 生成阶段可见的认证事实。

    这里只保留请求头名称和分析出的 header 候选，不返回登录接口候选或
    `login_flow` 之类会诱导模型生成认证步骤的模式。
    """

    raw_auth = _raw_auth_context(project_context, auth_context)
    environment = raw_auth.get("environment") if isinstance(raw_auth.get("environment"), dict) else {}
    configured_header_keys = _unique_strings(
        raw_auth.get("configured_header_keys"),
        environment.get("configured_header_keys"),
    )
    likely_auth_header_keys = _unique_strings(
        raw_auth.get("likely_auth_header_keys"),
        environment.get("likely_auth_header_keys"),
    )
    analysis_header_candidates = _unique_strings(
        raw_auth.get("analysis_header_candidates"),
        _repository_header_candidates(project_context),
    )
    return {
        "source": "dsl_generation",
        "mode": DSL_AUTH_MODE,
        "effective_mode": DSL_AUTH_MODE,
        "active_environment": _active_environment(project_context, raw_auth, environment),
        "configured_header_keys": configured_header_keys,
        "likely_auth_header_keys": likely_auth_header_keys,
        "analysis_header_candidates": analysis_header_candidates,
        "redacted": True,
        "reason": "用户通过项目请求头维护认证和登录态；DSL 只描述业务接口或页面步骤。",
        "generation_guidance": (
            "不要生成登录/登出步骤、认证接口、token/cookie/session 提取或认证 header 占位符。"
        ),
    }


def _default_project_context() -> dict[str, Any]:
    return {
        "version": "project_llm_context.v1",
        "auth": {},
        "repositories": [],
        "rules": [],
    }


def _raw_auth_context(
    project_context: dict[str, Any] | None,
    auth_context: dict[str, Any] | None,
) -> dict[str, Any]:
    if isinstance(auth_context, dict):
        return auth_context
    project_auth = (project_context or {}).get("auth")
    return project_auth if isinstance(project_auth, dict) else {}


def _active_environment(
    project_context: dict[str, Any] | None,
    raw_auth: dict[str, Any],
    environment: dict[str, Any],
) -> Any:
    if isinstance(project_context, dict) and project_context.get("active_environment"):
        return project_context.get("active_environment")
    return (
        raw_auth.get("active_environment")
        or environment.get("active_environment")
        or environment.get("environment")
    )


def _dsl_rules(value: Any) -> list[str]:
    rules = []
    if isinstance(value, list):
        rules = [
            str(rule)
            for rule in value
            if isinstance(rule, str) and not _is_auth_generation_rule(rule)
        ]
    return _unique_strings(_DSL_AUTH_RULES, rules)


def _is_auth_generation_rule(rule: str) -> bool:
    lowered = rule.lower()
    return any(marker.lower() in lowered for marker in _AUTH_RULE_MARKERS)


def _sanitize_repository(repository: dict[str, Any]) -> dict[str, Any]:
    sanitized = deepcopy(repository)
    auth_profile = sanitized.get("auth_profile")
    if isinstance(auth_profile, dict):
        sanitized["auth_profile"] = _sanitize_repository_auth_profile(auth_profile)
    return sanitized


def _sanitize_repository_auth_profile(auth_profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": auth_profile.get("source"),
        "repository_kind": auth_profile.get("repository_kind"),
        "mode_hint": DSL_AUTH_MODE,
        "header_candidates": _unique_strings(auth_profile.get("header_candidates")),
        "redacted": True,
        "reason": "登录候选接口不参与 DSL 生成；认证信息由项目请求头提供。",
    }


def _repository_header_candidates(project_context: dict[str, Any] | None) -> list[str]:
    repositories = (project_context or {}).get("repositories")
    if not isinstance(repositories, list):
        return []
    candidates: list[str] = []
    for repository in repositories:
        if not isinstance(repository, dict):
            continue
        auth_profile = repository.get("auth_profile")
        if isinstance(auth_profile, dict):
            candidates.extend(_string_values(auth_profile.get("header_candidates")))
    return candidates


def _unique_strings(*values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        for item in _string_values(value):
            if item not in seen:
                seen.add(item)
                result.append(item)
    return result


def _string_values(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
