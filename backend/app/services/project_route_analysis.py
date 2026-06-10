from __future__ import annotations

from collections import defaultdict
import re
from typing import Any

from app.services.repo_reader import RepoSummary

PROJECT_ROUTE_ANALYSIS_VERSION = "project_route_analysis.v1"
MAX_MODULES = 128
MAX_ROUTES_PER_MODULE = 32
MAX_RELATIONSHIPS = 300

DISCOVERY_TERMS = ("page", "list", "search", "query", "分页", "列表", "搜索", "查询")
DETAIL_TERMS = ("detail", "info", "home", "详情", "首页")
ACTION_TERMS = (
    "join",
    "complete",
    "exchange",
    "submit",
    "save",
    "create",
    "update",
    "加入",
    "完成",
    "兑换",
    "提交",
    "保存",
)
ID_FIELD_PATTERN = re.compile(r"(?:^|[A-Z_])(id|Id|ID)$")
ROUTE_PREFIX_SEGMENTS = {
    "api",
    "customer",
    "admin",
    "merchant",
    "pb",
    "pd",
    "private",
    "public",
    "open",
}
TERMINAL_ACTION_SEGMENTS = {
    "page",
    "list",
    "search",
    "query",
    "detail",
    "info",
    "home",
    "create",
    "update",
    "save",
    "submit",
    "delete",
    "remove",
}


def build_project_route_analysis(kind: str, summary: RepoSummary) -> dict[str, Any]:
    """把扁平路由目录归纳为可审核的模块和接口前后置关系。

    这里只使用项目扫描得到的路由、DTO、响应字段和源码位置作为证据。后续 AI
    或人工审核可以改模块归属和关系，但原始证据必须保留，避免再次退化成关键词猜测。
    """

    route_profiles = [_route_profile(route) for route in summary.routes]
    modules = _group_modules(route_profiles)
    relationships = [
        *_variable_relationships(route_profiles),
        *_path_related_module_relationships(route_profiles, modules),
    ]
    return {
        "version": PROJECT_ROUTE_ANALYSIS_VERSION,
        "kind": kind,
        "analysis_mode": "code_evidence_draft",
        "review": {
            "status": "draft",
            "human_review_required": True,
            "editable_fields": [
                "modules[].name",
                "modules[].scope_boundary",
                "modules[].routes[].role",
                "modules[].routes[].produces",
                "modules[].routes[].consumes",
                "relationships[].confirmed",
            ],
            "guidance": (
                "模块和关系来自代码证据归纳。人工复查时优先确认入口接口、子域排除条件、"
                "以及业务 ID 是否由前置响应生产。"
            ),
        },
        "modules": modules[:MAX_MODULES],
        "relationships": relationships[:MAX_RELATIONSHIPS],
        "relationship_guidance": (
            "生成 DSL 时优先使用已审核关系；未审核关系只能作为候选，必须继续保留 evidence。"
        ),
    }


def _route_profile(route: dict[str, Any]) -> dict[str, Any]:
    intent_text = _route_intent_text(route)
    consumes = _consumed_variables(route, intent_text)
    produces = _produced_variables(route, intent_text)
    return {
        "route": route,
        "text": intent_text,
        "role": _route_role(intent_text),
        "module": _route_module(route, intent_text),
        "produces": produces,
        "consumes": consumes,
    }


def _group_modules(route_profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    module_meta: dict[str, dict[str, Any]] = {}
    for profile in route_profiles:
        module = profile["module"]
        module_meta[module["id"]] = module
        grouped[module["id"]].append(profile)

    modules: list[dict[str, Any]] = []
    for module_id, profiles in grouped.items():
        meta = module_meta[module_id]
        prioritized_profiles = sorted(profiles, key=_module_route_sort_key)
        related_domains = _module_related_domains(profiles)
        routes = [
            _compact_route_profile(profile)
            for profile in prioritized_profiles[:MAX_ROUTES_PER_MODULE]
        ]
        modules.append(
            {
                "id": module_id,
                "name": meta["name"],
                "domain": meta["domain"],
                "route_count": len(profiles),
                "entrypoint_candidates": [
                    route
                    for route in routes
                    if route.get("role") == "discovery"
                ][:6],
                "routes": routes,
                "scope_boundary": _scope_boundary(meta["domain"], related_domains),
                "related_domains": related_domains,
                "evidence": _module_evidence(profiles),
                "review_status": "draft",
            }
        )

    modules.sort(key=lambda item: (-len(item["entrypoint_candidates"]), item["name"]))
    return modules


def _variable_relationships(route_profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    producers: dict[str, list[dict[str, Any]]] = defaultdict(list)
    consumers: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for profile in route_profiles:
        for variable in profile["produces"]:
            producers[variable].append(profile)
        for variable in profile["consumes"]:
            consumers[variable].append(profile)

    relationships: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for variable, consumer_profiles in consumers.items():
        for consumer in consumer_profiles:
            for producer in producers.get(variable, []):
                if producer["route"] is consumer["route"]:
                    continue
                key = (
                    variable,
                    str(producer["route"].get("path") or ""),
                    str(consumer["route"].get("path") or ""),
                )
                if key in seen:
                    continue
                seen.add(key)
                relationships.append(_relationship(variable, producer, consumer))

    relationships.sort(key=lambda item: item["confidence"], reverse=True)
    return relationships


def _path_related_module_relationships(
    route_profiles: list[dict[str, Any]],
    modules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    module_by_domain = {
        str(module.get("domain")): module
        for module in modules
        if module.get("domain")
    }
    relationships: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for profile in route_profiles:
        module = profile.get("module") if isinstance(profile.get("module"), dict) else {}
        source_module_id = str(module.get("id") or "")
        for related_domain in module.get("related_domains") or []:
            target = module_by_domain.get(str(related_domain))
            if not target or target.get("id") == source_module_id:
                continue
            key = (source_module_id, str(target["id"]), str(profile["route"].get("path") or ""))
            if key in seen:
                continue
            seen.add(key)
            relationships.append(_path_related_relationship(profile, target, str(related_domain)))
    return relationships


def _path_related_relationship(
    profile: dict[str, Any],
    target_module: dict[str, Any],
    related_domain: str,
) -> dict[str, Any]:
    target_route = _module_reference_route(target_module)
    return {
        "type": "module_reference",
        "variable": related_domain,
        "from_route": _route_identity(profile["route"]),
        "to_route": target_route,
        "from_module": profile["module"]["id"],
        "to_module": target_module["id"],
        "confidence": 0.66,
        "confirmed": False,
        "reason": "路径后续段命中另一个模块主域，表示当前接口可能涉及跨模块关联。",
        "evidence": [_evidence_text("module_reference", profile["route"])],
    }


def _module_reference_route(module: dict[str, Any]) -> dict[str, Any]:
    entrypoints = module.get("entrypoint_candidates")
    if isinstance(entrypoints, list):
        for route in entrypoints:
            if isinstance(route, dict):
                return route
    routes = module.get("routes")
    if isinstance(routes, list):
        for route in routes:
            if isinstance(route, dict):
                return route
    return {}


def _relationship(
    variable: str,
    producer: dict[str, Any],
    consumer: dict[str, Any],
) -> dict[str, Any]:
    confidence = 0.72
    reason = "生产方响应或入口语义可提供变量，消费方路径、query 或 body 需要该变量。"
    if producer["role"] == "discovery":
        confidence += 0.12
        reason = "生产方是分页/列表/搜索入口，消费方需要同名业务 ID。"
    if consumer["role"] in {"detail", "action"}:
        confidence += 0.08
    return {
        "type": "variable_flow",
        "variable": variable,
        "from_route": _route_identity(producer["route"]),
        "to_route": _route_identity(consumer["route"]),
        "from_module": producer["module"]["id"],
        "to_module": consumer["module"]["id"],
        "confidence": round(min(confidence, 0.95), 2),
        "confirmed": False,
        "reason": reason,
        "evidence": [
            _evidence_text("producer", producer["route"]),
            _evidence_text("consumer", consumer["route"]),
        ],
    }


def _route_module(route: dict[str, Any], text: str) -> dict[str, Any]:
    path = str(route.get("path") or "").lower()
    segments = _semantic_route_segments(path)
    family = segments[0] if segments else _route_family(path)
    related_segments = segments[1:]
    return {
        "id": f"module_{family or 'general'}",
        "name": _fallback_module_name([family]),
        "domain": family or "general",
        "scope_boundary": _scope_boundary(family, related_segments),
        "related_domains": related_segments,
    }


def _module_related_domains(profiles: list[dict[str, Any]]) -> list[str]:
    domains: list[str] = []
    for profile in profiles:
        module = profile.get("module")
        if not isinstance(module, dict):
            continue
        for domain in module.get("related_domains") or []:
            if isinstance(domain, str):
                domains.append(domain)
    return list(dict.fromkeys(domains))


def _module_route_sort_key(profile: dict[str, Any]) -> tuple[int, int, str]:
    route = profile["route"]
    path = str(route.get("path") or "").lower()
    score = 0
    if profile["role"] == "discovery":
        score += 20
    if _is_public_route(path):
        score += 10
    if _last_literal_segment(path) in DISCOVERY_TERMS:
        score += 18
    if _looks_like_management_route(path):
        score -= 16
    return (-score, len(path), path)


def _route_role(text: str) -> str:
    if _contains_any(text, DISCOVERY_TERMS):
        return "discovery"
    if _contains_any(text, DETAIL_TERMS):
        return "detail"
    if _contains_any(text, ACTION_TERMS):
        return "action"
    return "request"


def _consumed_variables(route: dict[str, Any], text: str) -> list[str]:
    variables: list[str] = []
    for variable in _path_variables(str(route.get("path") or "")):
        variables.append(_domain_variable(variable, text))
    for parameter in route.get("parameters") or []:
        if not isinstance(parameter, dict):
            continue
        name = str(parameter.get("name") or "")
        if _looks_like_id_field(name):
            variables.append(_domain_variable(name, text))
    request_body = route.get("request_body")
    if isinstance(request_body, dict):
        for field in _request_body_fields(request_body):
            if _looks_like_id_field(field):
                variables.append(_domain_variable(field, text))
    return _unique(variables)


def _produced_variables(route: dict[str, Any], text: str) -> list[str]:
    variables: list[str] = []
    for field in _response_fields(route.get("responses")):
        if _looks_like_id_field(field):
            variables.append(_domain_variable(field, text))

    role = _route_role(text)
    if role == "discovery" and not variables:
        resource = _primary_resource_segment(str(route.get("path") or ""))
        if resource:
            variables.append(_id_variable_for_segment(resource))
    return _unique(variables)


def _domain_variable(variable: str, text: str) -> str:
    normalized = variable.strip("{} ")
    if normalized in {"id", "Id", "ID"}:
        resource = _primary_resource_segment_from_text(text)
        if resource:
            return _id_variable_for_segment(resource)
    return normalized


def _compact_route_profile(profile: dict[str, Any]) -> dict[str, Any]:
    route = profile["route"]
    request_body = route.get("request_body")
    module = profile.get("module") if isinstance(profile.get("module"), dict) else {}
    return {
        **_route_identity(route),
        "role": profile["role"],
        "produces": profile["produces"],
        "consumes": profile["consumes"],
        "related_domains": module.get("related_domains", []),
        "request_body_fields": (
            _request_body_fields(request_body)[:12] if isinstance(request_body, dict) else []
        ),
        "evidence": [_evidence_text("route", route)],
    }


def _route_identity(route: dict[str, Any]) -> dict[str, Any]:
    return {
        "method": route.get("method"),
        "path": route.get("path"),
        "summary": route.get("summary") or route.get("log"),
        "handler": route.get("handler"),
        "source": route.get("source"),
    }


def _module_evidence(profiles: list[dict[str, Any]]) -> list[str]:
    evidence: list[str] = []
    for profile in profiles[:6]:
        evidence.append(_evidence_text("module", profile["route"]))
    return evidence


def _evidence_text(kind: str, route: dict[str, Any]) -> str:
    method = str(route.get("method") or "GET")
    path = str(route.get("path") or "")
    summary = str(route.get("summary") or route.get("log") or route.get("handler") or "")
    source = str(route.get("source") or "")
    return f"{kind}: {method} {path}；{summary}；source={source}"


def _route_text(route: dict[str, Any]) -> str:
    values = [
        route.get("method"),
        route.get("path"),
        route.get("summary"),
        route.get("log"),
        route.get("handler"),
        route.get("source"),
        route.get("parameters"),
        route.get("request_body"),
        route.get("responses"),
    ]
    return " ".join(str(value or "") for value in values).lower()


def _route_intent_text(route: dict[str, Any]) -> str:
    values = [
        route.get("method"),
        route.get("path"),
        route.get("summary"),
        route.get("log"),
        route.get("handler"),
        route.get("tags"),
    ]
    return " ".join(str(value or "") for value in values).lower()


def _route_family(path: str) -> str:
    parts = [part for part in path.split("/") if part]
    if "api" in parts:
        parts = parts[parts.index("api") + 1 :]
    parts = [part for part in parts if part not in {"pb", "pd", "private", "public"}]
    return re.sub(r"[^a-z0-9_]+", "_", parts[0]) if parts else ""


def _fallback_module_name(segments: list[str]) -> str:
    if not segments:
        return "未归类接口"
    return " / ".join(segments) + " 模块"


def _scope_boundary(family: str, related_segments: list[str]) -> str | None:
    if not family or not related_segments:
        return None
    return (
        f"该模块按主路径段 `{family}` 归类；后续路径段 `{ '/'.join(related_segments) }` "
        "仅作为动作、子域或跨模块关联线索，不能单独拆成模块。"
    )


def _contains_any(value: str, tokens: tuple[str, ...]) -> bool:
    return any(token.lower() in value for token in tokens)


def _path_variables(path: str) -> list[str]:
    return re.findall(r"\{([^/{}]+)\}", path)


def _semantic_route_segments(path: str) -> list[str]:
    segments = []
    for raw in path.lower().split("/"):
        segment = raw.strip()
        if not segment or segment in ROUTE_PREFIX_SEGMENTS:
            continue
        if re.fullmatch(r"\{[^/{}]+\}", segment):
            continue
        if segment in TERMINAL_ACTION_SEGMENTS:
            continue
        segments.append(re.sub(r"[^a-z0-9_]+", "_", segment).strip("_"))
    return [segment for segment in segments if segment]


def _primary_resource_segment(path: str) -> str | None:
    segments = _semantic_route_segments(path)
    return segments[-1] if segments else None


def _primary_resource_segment_from_text(text: str) -> str | None:
    match = re.search(r"(/[a-z0-9_{}.-]+)+", text)
    return _primary_resource_segment(match.group(0)) if match else None


def _id_variable_for_segment(segment: str) -> str:
    words = [word for word in re.split(r"[_\-.]+", segment) if word]
    if not words:
        return "entityId"
    first, *rest = words
    camel = _singularize(first) + "".join(word[:1].upper() + word[1:] for word in rest)
    return f"{camel}Id"


def _singularize(value: str) -> str:
    if value.endswith("ies") and len(value) > 4:
        return value[:-3] + "y"
    if value.endswith("s") and len(value) > 3:
        return value[:-1]
    return value


def _is_public_route(path: str) -> bool:
    parts = {part for part in path.split("/") if part}
    return bool(parts & {"pb", "public", "open"})


def _looks_like_management_route(path: str) -> bool:
    parts = {part for part in path.split("/") if part}
    return bool(parts & {"admin", "merchant", "manage", "management", "backoffice"})


def _last_literal_segment(path: str) -> str:
    parts = [part for part in path.lower().split("/") if part and not part.startswith("{")]
    return parts[-1] if parts else ""


def _request_body_fields(request_body: dict[str, Any]) -> list[str]:
    schema = request_body.get("schema")
    if not isinstance(schema, dict):
        return []
    properties = schema.get("properties")
    return [str(field) for field in properties] if isinstance(properties, dict) else []


def _response_fields(responses: Any) -> list[str]:
    fields: list[str] = []
    if not isinstance(responses, list):
        return fields
    for response in responses:
        if isinstance(response, dict) and isinstance(response.get("fields"), list):
            fields.extend(str(field) for field in response["fields"])
    return fields


def _looks_like_id_field(value: str) -> bool:
    return bool(value and (ID_FIELD_PATTERN.search(value) or value.lower().endswith("_id")))


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
