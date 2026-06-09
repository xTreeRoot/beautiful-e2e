from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.services.api_route_matching import route_matches_target, strip_gateway_prefix, url_path
from app.services.case_generation_types import GeneratedCase, GeneratedStep

AUTH_GUIDANCE_TERMS = (
    "登录态",
    "登录",
    "登陆",
    "authorization",
    "auth",
    "token",
    "cookie",
    "session",
    "satoken",
    "匿名可调",
    "请求头",
    "认证",
)

API_NAMESPACE_SEGMENTS = {
    "api",
    "pb",
    "pd",
    "public",
    "private",
    "open",
    "customer",
    "merchant",
    "admin",
    "v1",
    "v2",
    "v3",
}


def sanitize_backend_api_steps(
    generated: GeneratedCase,
    routes: list[dict[str, Any]],
) -> GeneratedCase:
    """移除模型误生成的非接口说明节点。

    认证、登录态和请求头说明由项目配置承载，不属于 DSL 执行步骤。这里作为
    prompt 之外的最后防线，避免模型把文档里的说明文本包装成 `api_request`
    后进入画布。
    """

    next_steps: list[GeneratedStep] = []
    dropped_steps: list[dict[str, Any]] = []
    for step in generated.steps:
        if step.action != "api_request":
            next_steps.append(step)
            continue
        data = dict(step.data or {})
        reason = _non_executable_reason(step, data, routes)
        if reason:
            dropped_steps.append(_dropped_step_payload(step, data, reason))
            continue
        next_steps.append(step)

    if not dropped_steps:
        return generated

    context = dict(generated.code_context or {})
    context["dropped_non_executable_api_steps"] = {
        "reason": "生成结果包含认证说明或网关前缀伪接口，保存前已移除。",
        "items": dropped_steps[:50],
    }
    return replace(generated, steps=next_steps, code_context=context)


def has_executable_api_step(generated: GeneratedCase) -> bool:
    """判断生成结果是否仍包含可执行接口步骤。"""

    return any(step.action == "api_request" for step in generated.steps)


def _non_executable_reason(
    step: GeneratedStep,
    data: dict[str, Any],
    routes: list[dict[str, Any]],
) -> str | None:
    target_path = strip_gateway_prefix(url_path(step.target_url or ""))
    template_path = strip_gateway_prefix(
        url_path(str(data.get("route_path_template") or data.get("document_path_template") or ""))
    )
    if _is_bare_api_namespace(target_path) or (
        bool(template_path) and _is_bare_api_namespace(template_path)
    ):
        return "接口路径只是网关或开放域前缀，不是可执行业务接口。"
    if _is_auth_guidance_step(step, data) and not _matches_known_route(step, routes):
        return "该节点是认证、登录态或请求头说明，不是需要写入 DSL 的接口步骤。"
    return None


def _is_bare_api_namespace(path: str) -> bool:
    parts = [part.lower() for part in path.split("/") if part]
    if not parts:
        return True
    if parts[0] != "api":
        return False
    return len(parts) <= 2 and all(part in API_NAMESPACE_SEGMENTS for part in parts)


def _is_auth_guidance_step(step: GeneratedStep, data: dict[str, Any]) -> bool:
    text = " ".join(
        str(value or "")
        for value in [
            step.label,
            step.expected,
            data.get("route_summary"),
            data.get("flow_reason"),
            data.get("reference_excerpt"),
            data.get("route_decision"),
        ]
    ).lower()
    return any(term.lower() in text for term in AUTH_GUIDANCE_TERMS)


def _matches_known_route(step: GeneratedStep, routes: list[dict[str, Any]]) -> bool:
    return any(route_matches_target(route, step.target_url) for route in routes)


def _dropped_step_payload(
    step: GeneratedStep,
    data: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    return {
        "label": step.label,
        "method": data.get("method"),
        "target_url": step.target_url,
        "route_path_template": data.get("route_path_template"),
        "route_summary": data.get("route_summary"),
        "reason": reason,
    }
