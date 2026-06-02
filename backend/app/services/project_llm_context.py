from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Repository
from app.services.environment_auth import (
    build_environment_auth_context,
    likely_auth_header_keys_from_headers,
)
from app.services.repo_reader import RepoSummary

PROJECT_LLM_CONTEXT_VERSION = "project_llm_context.v1"
PROJECT_CONTEXT_ROUTE_CONTRACT_LIMIT = 24
PROJECT_CONTEXT_ROUTE_FIELD_LIMIT = 24

LOGIN_ROUTE_TERMS = (
    "login",
    "signin",
    "sign-in",
    "auth",
    "token",
    "session",
    "登录",
    "登陆",
    "授权",
)

EXTERNAL_AUTH_TERMS = (
    "wechat",
    "weixin",
    "wx",
    "miniapp",
    "mp",
    "openid",
    "unionid",
    "oauth",
    "sso",
    "sms",
    "captcha",
    "qrcode",
    "scan",
    "小程序",
    "微信",
    "扫码",
    "验证码",
    "第三方",
)


def build_project_llm_context(
    project_id: str,
    project_settings: dict[str, Any],
    db: Session,
    repository_summaries: dict[str, RepoSummary] | None = None,
) -> dict[str, Any]:
    """构建所有 LLM 共享的项目级上下文。

    上下文只包含项目事实、分析结论和脱敏后的环境信息，不包含真实 token、
    cookie 或密码。生成、运行期辅助测试以及后续新增 LLM 都应从这里取项目画像。
    """

    repositories = list(
        db.scalars(select(Repository).where(Repository.project_id == project_id)).all()
    )
    environment_auth = build_environment_auth_context(project_settings)
    summary_profiles = {
        kind: _summary_auth_profile(kind, summary)
        for kind, summary in (repository_summaries or {}).items()
    }
    repository_profiles = [
        *summary_profiles.values(),
        *[_repository_auth_profile(repo) for repo in repositories if repo.kind not in summary_profiles],
    ]
    auth_profile = merge_project_auth_profiles(environment_auth, repository_profiles)

    return {
        "version": PROJECT_LLM_CONTEXT_VERSION,
        "project_id": project_id,
        "active_environment": environment_auth.get("active_environment"),
        "auth": auth_profile,
        "repositories": [
            *[_summary_context(kind, summary) for kind, summary in (repository_summaries or {}).items()],
            *[_repository_context(repo) for repo in repositories if repo.kind not in summary_profiles],
        ],
        "rules": [
            "所有 LLM 必须优先遵守 project_llm_context.auth.effective_mode。",
            "环境请求头只暴露 key，不暴露真实值；不要把真实 token、cookie 或密码写入 DSL。",
            "登录态可以来自环境请求头或可执行登录接口；业务实体 ID 仍必须来自前置响应或显式测试夹具。",
            "如果生成输入提供 reference_fixtures，必须先使用其中固定 ID、活动名、商品名或页面标题，不要从提示词短词猜实体。",
            "接口参数必须以 repository.route_contract_examples 或 backend_repository_summary.routes 中的 parameters/request_body 为准。",
            "生成分页或搜索 body 时禁止把 page/limit/goodsName 猜成 current/size/keyword，除非真实 DTO 明确存在这些字段。",
            "运行期辅助 LLM 只能从 previous_responses 抽取变量，不能用项目画像编造缺失值。",
            "后续收到 api_generation_feedback 时，必须把 404、未知处理器和变量未推导视为反例证据，重新回到项目路径内的真实路由和参数契约。",
        ],
    }


def analyze_repository_auth_profile(kind: str, summary: RepoSummary) -> dict[str, Any]:
    """根据项目分析结果初判登录方式。

    这是确定性画像，不替代真实运行验证。它的职责是给后续 LLM 一个一致的
    默认判断：是否存在可接口化登录、是否更像外部/小程序登录、有哪些 header
    可能承载认证。
    """

    login_routes = [_compact_route(route) for route in summary.routes if _is_login_route(route)]
    header_candidates = sorted(
        {
            header
            for route in summary.routes
            for header in _auth_header_parameters(route)
        }
    )
    evidence = _auth_signal_evidence(summary, login_routes, header_candidates)
    if login_routes and any(_contains_external_auth_term(route) for route in login_routes):
        mode_hint = "external_or_environment_headers"
        confidence = 0.78
        reason = "发现登录相关接口，但路径或摘要包含小程序、第三方、OAuth、验证码等外部登录线索。"
    elif login_routes:
        mode_hint = "login_flow"
        confidence = 0.82
        reason = "发现可执行登录或换取 token 的候选接口。"
    elif header_candidates:
        mode_hint = "environment_headers"
        confidence = 0.7
        reason = "接口契约里存在认证相关 header 参数，但没有发现明确登录接口。"
    elif any(_contains_external_auth_term(signal) for signal in summary.signals):
        mode_hint = "external_or_environment_headers"
        confidence = 0.62
        reason = "仓库信号包含小程序、第三方或外部登录线索，但没有发现可执行登录接口。"
    else:
        mode_hint = "unknown"
        confidence = 0.3 if summary.exists else 0.0
        reason = "项目分析未发现稳定登录方式。"

    return {
        "source": "project_analysis",
        "repository_kind": kind,
        "mode_hint": mode_hint,
        "confidence": confidence,
        "reason": reason,
        "login_route_candidates": login_routes[:8],
        "header_candidates": header_candidates,
        "evidence": evidence[:8],
    }


def merge_project_auth_profiles(
    environment_auth: dict[str, Any],
    repository_profiles: list[dict[str, Any]],
) -> dict[str, Any]:
    """合并环境配置和项目分析，形成统一认证画像。"""

    configured_header_keys = list(environment_auth.get("configured_header_keys") or [])
    likely_auth_header_keys = list(environment_auth.get("likely_auth_header_keys") or [])
    login_candidates = [
        route
        for profile in repository_profiles
        for route in profile.get("login_route_candidates", [])
        if isinstance(route, dict)
    ]
    header_candidates = sorted(
        {
            str(header)
            for profile in repository_profiles
            for header in profile.get("header_candidates", [])
            if str(header).strip()
        }
    )
    profile_hints = [str(profile.get("mode_hint") or "") for profile in repository_profiles]

    if environment_auth.get("mode") == "environment_headers":
        effective_mode = "environment_headers"
        confidence = 1.0
        reason = "当前接口环境已配置非空认证请求头，运行时优先由环境注入登录态。"
    elif "login_flow" in profile_hints:
        effective_mode = "login_flow"
        confidence = _max_profile_confidence(repository_profiles, "login_flow")
        reason = "项目分析发现可执行登录或换取 token 的候选接口。"
    elif "external_or_environment_headers" in profile_hints:
        effective_mode = "external_or_environment_headers"
        confidence = _max_profile_confidence(repository_profiles, "external_or_environment_headers")
        reason = "项目分析显示登录可能依赖小程序、第三方、验证码或外部会话。"
    elif "environment_headers" in profile_hints:
        effective_mode = "environment_headers_required"
        confidence = _max_profile_confidence(repository_profiles, "environment_headers")
        reason = "接口契约提示需要认证 header，但当前环境未配置非空登录态。"
    elif environment_auth.get("mode") == "configured_headers":
        effective_mode = "configured_headers"
        confidence = 0.75
        reason = "当前环境配置了通用请求头，运行时会自动注入，但未确认它们是否承载登录态。"
    else:
        effective_mode = "unknown"
        confidence = max((float(profile.get("confidence") or 0) for profile in repository_profiles), default=0.0)
        reason = "尚未从环境配置或项目分析中确认登录方式。"

    return {
        "source": "project_llm_context",
        "environment": environment_auth,
        "effective_mode": effective_mode,
        "confidence": confidence,
        "reason": reason,
        "configured_header_keys": configured_header_keys,
        "likely_auth_header_keys": likely_auth_header_keys or header_candidates,
        "analysis_header_candidates": header_candidates,
        "login_route_candidates": login_candidates[:8],
        "repository_profiles": repository_profiles,
        "generation_guidance": _generation_guidance(effective_mode),
        "runtime_guidance": _runtime_guidance(effective_mode),
        "redacted": True,
    }


def _repository_auth_profile(repo: Repository) -> dict[str, Any]:
    summary = repo.index_summary if isinstance(repo.index_summary, dict) else {}
    profile = summary.get("auth_profile")
    if isinstance(profile, dict):
        return profile
    return analyze_repository_auth_profile(repo.kind, RepoSummary.from_dict(summary))


def _summary_auth_profile(kind: str, summary: RepoSummary) -> dict[str, Any]:
    if isinstance(summary.auth_profile, dict):
        return summary.auth_profile
    return analyze_repository_auth_profile(kind, summary)


def _repository_context(repo: Repository) -> dict[str, Any]:
    summary = repo.index_summary if isinstance(repo.index_summary, dict) else {}
    analysis = summary.get("analysis") if isinstance(summary.get("analysis"), dict) else {}
    routes = summary.get("routes") if isinstance(summary.get("routes"), list) else []
    dom_targets = summary.get("dom_targets") if isinstance(summary.get("dom_targets"), list) else []
    profile = summary.get("auth_profile") if isinstance(summary.get("auth_profile"), dict) else None
    return {
        "kind": repo.kind,
        "path": repo.path,
        "exists": bool(summary.get("exists")),
        "analysis": analysis,
        "route_count": len(routes),
        "dom_target_count": len(dom_targets),
        "route_contract_profile": _route_contract_profile(routes),
        "route_contract_examples": _route_contract_examples(routes),
        "auth_profile": profile,
    }


def _summary_context(kind: str, summary: RepoSummary) -> dict[str, Any]:
    return {
        "kind": kind,
        "path": summary.path,
        "exists": summary.exists,
        "analysis": {},
        "route_count": len(summary.routes),
        "dom_target_count": len(summary.dom_targets),
        "route_contract_profile": _route_contract_profile(summary.routes),
        "route_contract_examples": _route_contract_examples(summary.routes),
        "auth_profile": _summary_auth_profile(kind, summary),
    }


def _route_contract_profile(routes: list[dict[str, Any]]) -> dict[str, Any]:
    request_body_routes = [route for route in routes if isinstance(route.get("request_body"), dict)]
    parameter_routes = [route for route in routes if isinstance(route.get("parameters"), list)]
    body_field_names = sorted(
        {
            field
            for route in request_body_routes
            for field in _request_body_fields(route.get("request_body"))
        }
    )
    return {
        "route_count": len(routes),
        "parameter_route_count": len(parameter_routes),
        "request_body_route_count": len(request_body_routes),
        "body_field_names": body_field_names[:PROJECT_CONTEXT_ROUTE_FIELD_LIMIT],
        "guidance": (
            "这些字段来自项目分析阶段扫描到的真实路由/DTO 契约；生成 DSL 时只能使用契约字段，"
            "不要按其他框架习惯替换分页、搜索或 ID 字段名。"
        ),
    }


def _route_contract_examples(routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for route in routes:
        compact = _compact_route_contract(route)
        if not compact:
            continue
        examples.append(compact)
        if len(examples) >= PROJECT_CONTEXT_ROUTE_CONTRACT_LIMIT:
            break
    return examples


def _compact_route_contract(route: dict[str, Any]) -> dict[str, Any] | None:
    request_body = route.get("request_body")
    parameters = route.get("parameters")
    if not isinstance(request_body, dict) and not isinstance(parameters, list):
        return None

    compact: dict[str, Any] = _compact_route(route)
    if isinstance(parameters, list) and parameters:
        compact["parameters"] = [
            {
                "name": item.get("name"),
                "in": item.get("in"),
                "required": item.get("required"),
                "type": (item.get("schema") or {}).get("type") if isinstance(item.get("schema"), dict) else None,
            }
            for item in parameters[:PROJECT_CONTEXT_ROUTE_FIELD_LIMIT]
            if isinstance(item, dict)
        ]
    if isinstance(request_body, dict):
        fields = _request_body_fields(request_body)
        compact["request_body"] = {
            "required": request_body.get("required"),
            "java_type": request_body.get("java_type"),
            "fields": fields[:PROJECT_CONTEXT_ROUTE_FIELD_LIMIT],
            "required_fields": _request_body_required_fields(request_body),
            "example": request_body.get("example") if isinstance(request_body.get("example"), dict) else None,
            "source": request_body.get("source"),
        }
    return compact


def _request_body_fields(request_body: Any) -> list[str]:
    if not isinstance(request_body, dict):
        return []
    schema = request_body.get("schema")
    if not isinstance(schema, dict):
        return []
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return []
    return [str(field) for field in properties]


def _request_body_required_fields(request_body: Any) -> list[str]:
    if not isinstance(request_body, dict):
        return []
    schema = request_body.get("schema")
    if not isinstance(schema, dict):
        return []
    required = schema.get("required")
    return [str(item) for item in required] if isinstance(required, list) else []


def _compact_route(route: dict[str, Any]) -> dict[str, Any]:
    return {
        "method": route.get("method"),
        "path": route.get("path"),
        "summary": route.get("summary") or route.get("description"),
        "handler": route.get("handler"),
        "source": route.get("source"),
    }


def _is_login_route(route: dict[str, Any]) -> bool:
    text = _route_text(route)
    return any(term in text for term in LOGIN_ROUTE_TERMS)


def _route_text(route: dict[str, Any]) -> str:
    values = [
        route.get("path"),
        route.get("summary"),
        route.get("description"),
        route.get("handler"),
        route.get("log"),
        " ".join(str(tag) for tag in route.get("tags", []) if isinstance(tag, str)),
    ]
    return " ".join(str(value) for value in values if value).lower()


def _auth_header_parameters(route: dict[str, Any]) -> list[str]:
    parameters = route.get("parameters")
    if not isinstance(parameters, list):
        return []
    headers: list[str] = []
    for parameter in parameters:
        if not isinstance(parameter, dict) or str(parameter.get("in") or "").lower() != "header":
            continue
        name = str(parameter.get("name") or "").strip()
        if name:
            headers.extend(likely_auth_header_keys_from_headers({name: "configured"}))
    return headers


def _auth_signal_evidence(
    summary: RepoSummary,
    login_routes: list[dict[str, Any]],
    header_candidates: list[str],
) -> list[str]:
    evidence = [
        f"候选登录接口：{route.get('method')} {route.get('path')}"
        for route in login_routes[:4]
    ]
    evidence.extend(f"认证请求头参数：{header}" for header in header_candidates[:4])
    evidence.extend(signal for signal in summary.signals if _contains_auth_term(signal))
    return evidence


def _contains_auth_term(value: Any) -> bool:
    text = str(value).lower()
    return any(term in text for term in (*LOGIN_ROUTE_TERMS, *EXTERNAL_AUTH_TERMS))


def _contains_external_auth_term(value: Any) -> bool:
    text = str(value).lower()
    return any(term in text for term in EXTERNAL_AUTH_TERMS)


def _max_profile_confidence(profiles: list[dict[str, Any]], mode_hint: str) -> float:
    return max(
        (float(profile.get("confidence") or 0) for profile in profiles if profile.get("mode_hint") == mode_hint),
        default=0.0,
    )


def _generation_guidance(effective_mode: str) -> str:
    if effective_mode == "environment_headers":
        return "生成 DSL 时不要为环境认证 header 生成 token 占位符，也不要强行插入登录接口。"
    if effective_mode == "login_flow":
        return "可以优先使用候选登录接口建立 token extract，再让后续接口消费该变量。"
    if effective_mode == "external_or_environment_headers":
        return "登录可能依赖小程序、三方或验证码；优先提示用户配置环境请求头，不要臆造登录链路。"
    if effective_mode == "environment_headers_required":
        return "接口契约需要认证 header，但当前环境未提供值；生成 DSL 时应标记认证缺口。"
    return "登录方式不明确；只有证据充分时才生成登录步骤，否则写入 unresolved_parameters。"


def _runtime_guidance(effective_mode: str) -> str:
    if effective_mode == "environment_headers":
        return "运行期辅助 LLM 不要从前序响应推导环境认证 header，只能推导业务变量。"
    if effective_mode == "login_flow":
        return "运行期辅助 LLM 只能从已执行登录或前置接口响应中抽取 token。"
    return "运行期辅助 LLM 只能从 previous_responses 抽取变量，不能根据项目画像编造值。"
