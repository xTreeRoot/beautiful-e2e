from __future__ import annotations

from copy import deepcopy
import json
import re
from typing import Any

CODEX_EXEC_PROMPT_TARGET_CHARS = 850_000
HTTP_BRIDGE_PROMPT_TARGET_CHARS = 140_000
HTTP_BRIDGE_RETRY_PROMPT_TARGET_CHARS = 48_000
TRUNCATED_SUFFIX = "...[已截断]"


def compact_codex_exec_payload(
    payload: dict[str, Any],
    *,
    execution_mode: str,
    target_chars: int = CODEX_EXEC_PROMPT_TARGET_CHARS,
) -> dict[str, Any]:
    """把用例生成载荷压缩到 `codex exec` 非交互输入上限以内。

    Codex CLI 会在 turn/start 前校验完整 stdin 长度；压缩只裁剪高噪声仓库索引，
    保留路由路径、方法、字段名、认证画像和引用文档证据，避免失败后退回规则生成器。
    """
    return _compact_generation_payload(
        payload,
        execution_mode=execution_mode,
        target_chars=target_chars,
        provider="codex_exec",
        reason="codex exec stdin 有 1MB 左右硬上限，已压缩仓库索引中的大字段。",
    )


def compact_http_bridge_payload(
    payload: dict[str, Any],
    *,
    execution_mode: str,
    target_chars: int = HTTP_BRIDGE_PROMPT_TARGET_CHARS,
    provider: str = "codex_bridge",
    retry: bool = False,
) -> dict[str, Any]:
    """压缩 HTTP 桥接发送给模型的上下文。

    HTTP 供应商不会在本地提前知道真实 token 窗口；这里使用偏保守的字符预算，
    保留接口契约、引用文档摘要和变量链路证据，先剪掉高噪声索引，避免供应商返回
    context_length_exceeded 后直接降级到规则生成器。
    """

    reason = (
        "HTTP 供应商返回上下文超限，已使用更严格预算重试。"
        if retry
        else "HTTP 供应商上下文窗口有限，已预先压缩仓库索引和引用材料。"
    )
    return _compact_generation_payload(
        payload,
        execution_mode=execution_mode,
        target_chars=target_chars,
        provider=provider,
        reason=reason,
        retry=retry,
    )


def payload_json_chars(value: Any) -> int:
    """返回供应商载荷的 JSON 字符数，供重试策略比较压缩幅度。"""

    return _json_chars(value)


def _compact_generation_payload(
    payload: dict[str, Any],
    *,
    execution_mode: str,
    target_chars: int,
    provider: str,
    reason: str,
    retry: bool = False,
) -> dict[str, Any]:
    if _json_chars(payload) <= target_chars:
        return payload

    compacted = deepcopy(payload)
    backend_api = execution_mode == "backend_api"
    relevance_text = _payload_relevance_text(payload)
    compacted["frontend_repository_summary"] = _compact_repo_summary(
        compacted.get("frontend_repository_summary"),
        route_limit=40 if backend_api else 180,
        dom_target_limit=80 if backend_api else 180,
        relevance_text=relevance_text,
    )
    compacted["backend_repository_summary"] = _compact_repo_summary(
        compacted.get("backend_repository_summary"),
        route_limit=360 if backend_api else 220,
        dom_target_limit=40 if backend_api else 120,
        relevance_text=relevance_text,
    )
    compacted["project_context"] = _compact_project_context(compacted.get("project_context"))
    compacted["context_compaction"] = {
        "provider": provider,
        "reason": reason,
        "original_chars": _json_chars(payload),
        "target_chars": target_chars,
        "retry": retry,
    }

    if _json_chars(compacted) > target_chars:
        compacted["current_canvas_dsl"] = _bounded_value(
            compacted.get("current_canvas_dsl"),
            max_string_chars=600,
            max_list_items=120,
            max_object_items=60,
        )

    if _json_chars(compacted) > target_chars:
        compacted["reference_documents"] = _compact_reference_documents(
            compacted.get("reference_documents"),
            max_content_chars=2_000,
        )

    if _json_chars(compacted) > target_chars:
        compacted["backend_repository_summary"] = _compact_repo_summary(
            compacted.get("backend_repository_summary"),
            route_limit=180,
            dom_target_limit=24,
            relevance_text=relevance_text,
        )
        compacted["frontend_repository_summary"] = _compact_repo_summary(
            compacted.get("frontend_repository_summary"),
            route_limit=24,
            dom_target_limit=48,
            relevance_text=relevance_text,
        )

    if _json_chars(compacted) > target_chars:
        compacted["current_canvas_dsl"] = _bounded_value(
            compacted.get("current_canvas_dsl"),
            max_string_chars=240,
            max_list_items=40,
            max_object_items=40,
        )
        compacted["reference_documents"] = _compact_reference_documents(
            compacted.get("reference_documents"),
            max_content_chars=800,
        )

    while _json_chars(compacted) > target_chars and _halve_compacted_routes(compacted):
        continue

    if _json_chars(compacted) > target_chars:
        compacted["project_context"] = _bounded_value(
            compacted.get("project_context"),
            max_string_chars=180,
            max_list_items=12,
            max_object_items=32,
        )
        compacted["selected_agent"] = _bounded_value(
            compacted.get("selected_agent"),
            max_string_chars=180,
            max_list_items=12,
            max_object_items=24,
        )
        compacted["enabled_skills"] = _bounded_value(
            compacted.get("enabled_skills"),
            max_string_chars=180,
            max_list_items=8,
            max_object_items=24,
        )
        compacted["reference_documents"] = _compact_reference_documents(
            compacted.get("reference_documents"),
            max_content_chars=360,
        )
        compacted["backend_repository_summary"] = _compact_repo_summary(
            compacted.get("backend_repository_summary"),
            route_limit=48 if backend_api else 32,
            dom_target_limit=8 if backend_api else 32,
            relevance_text=relevance_text,
        )
        compacted["frontend_repository_summary"] = _compact_repo_summary(
            compacted.get("frontend_repository_summary"),
            route_limit=8 if backend_api else 32,
            dom_target_limit=24 if backend_api else 48,
            relevance_text=relevance_text,
        )

    while _json_chars(compacted) > target_chars and _halve_compacted_routes(
        compacted,
        min_limits={"backend_repository_summary": 8, "frontend_repository_summary": 4},
    ):
        continue

    compacted["context_compaction"]["compacted_chars"] = _json_chars(compacted)
    return compacted


def _compact_repo_summary(
    value: Any,
    *,
    route_limit: int,
    dom_target_limit: int,
    relevance_text: str = "",
) -> Any:
    if not isinstance(value, dict):
        return value
    routes = value.get("routes")
    dom_targets = value.get("dom_targets")
    selected_routes = _prioritized_items(
        routes,
        route_limit,
        relevance_text,
        item_text=_route_relevance_text,
    )
    selected_dom_targets = _prioritized_items(
        dom_targets,
        dom_target_limit,
        relevance_text,
        item_text=_dom_target_relevance_text,
    )
    compacted: dict[str, Any] = {
        "path": value.get("path"),
        "exists": value.get("exists"),
        "files": _string_list(value.get("files"), 120, 180),
        "signals": _string_list(value.get("signals"), 32, 360),
        "routes": [
            _compact_route(route)
            for route in selected_routes
            if isinstance(route, dict)
        ]
        if isinstance(selected_routes, list)
        else [],
        "dom_targets": [
            _compact_dom_target(target)
            for target in selected_dom_targets
            if isinstance(target, dict)
        ]
        if isinstance(selected_dom_targets, list)
        else [],
    }
    if isinstance(value.get("auth_profile"), dict):
        compacted["auth_profile"] = _compact_auth_profile(value["auth_profile"])
    return compacted


def _compact_route(route: dict[str, Any]) -> dict[str, Any]:
    compacted: dict[str, Any] = {
        "method": route.get("method"),
        "path": route.get("path"),
        "summary": _trim_text(route.get("summary") or route.get("description"), 180),
        "handler": route.get("handler"),
        "source": _trim_text(route.get("source"), 220),
    }
    tags = route.get("tags")
    if isinstance(tags, list) and tags:
        compacted["tags"] = [str(tag)[:80] for tag in tags[:8] if isinstance(tag, str)]
    parameters = route.get("parameters")
    if isinstance(parameters, list) and parameters:
        compacted["parameters"] = [
            _compact_parameter(parameter)
            for parameter in parameters[:32]
            if isinstance(parameter, dict)
        ]
    request_body = route.get("request_body")
    if isinstance(request_body, dict):
        compacted["request_body"] = _compact_request_body(request_body)
    responses = route.get("responses")
    if isinstance(responses, list) and responses:
        compacted["responses"] = [
            _compact_response(response)
            for response in responses[:8]
            if isinstance(response, dict)
        ]
    return {key: value for key, value in compacted.items() if value not in (None, "", [], {})}


def _compact_parameter(parameter: dict[str, Any]) -> dict[str, Any]:
    schema = parameter.get("schema")
    return {
        "name": parameter.get("name"),
        "in": parameter.get("in"),
        "required": parameter.get("required"),
        "type": parameter.get("type") or _schema_type(schema),
        "description": _trim_text(parameter.get("description"), 160),
    }


def _compact_request_body(request_body: dict[str, Any]) -> dict[str, Any]:
    fields = request_body.get("fields")
    required_fields = request_body.get("required_fields")
    return {
        "required": request_body.get("required"),
        "java_type": request_body.get("java_type"),
        "fields": (
            [str(field) for field in fields]
            if isinstance(fields, list)
            else _request_body_fields(request_body)
        )[:48],
        "required_fields": (
            [str(field) for field in required_fields]
            if isinstance(required_fields, list)
            else _request_body_required_fields(request_body)
        )[:48],
        "example_keys": _object_keys(request_body.get("example"), 32),
        "source": _trim_text(request_body.get("source"), 220),
    }


def _compact_response(response: dict[str, Any]) -> dict[str, Any]:
    fields = response.get("fields")
    return {
        "status": response.get("status") or response.get("code"),
        "description": _trim_text(response.get("description") or response.get("summary"), 160),
        "fields": (
            [str(field) for field in fields]
            if isinstance(fields, list)
            else _schema_fields(response.get("schema"))
        )[:32],
    }


def _compact_dom_target(target: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": target.get("kind"),
        "value": _trim_text(target.get("value"), 120),
        "source": _trim_text(target.get("source"), 180),
        "hint": _trim_text(target.get("hint"), 180),
    }


def _compact_project_context(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    compacted = deepcopy(value)
    repositories = compacted.get("repositories")
    if isinstance(repositories, list):
        compacted["repositories"] = [
            _compact_project_repository(repository)
            for repository in repositories[:6]
            if isinstance(repository, dict)
        ]
    knowledge_graph = compacted.get("knowledge_graph")
    if isinstance(knowledge_graph, dict):
        compacted["knowledge_graph"] = _compact_knowledge_graph(knowledge_graph)
    return compacted


def _compact_project_repository(repository: dict[str, Any]) -> dict[str, Any]:
    compacted = {
        "kind": repository.get("kind"),
        "path": repository.get("path"),
        "exists": repository.get("exists"),
        "analysis": _compact_project_analysis(repository.get("analysis")),
        "route_count": repository.get("route_count"),
        "dom_target_count": repository.get("dom_target_count"),
        "route_contract_profile": repository.get("route_contract_profile"),
    }
    if isinstance(repository.get("auth_profile"), dict):
        compacted["auth_profile"] = _compact_auth_profile(repository["auth_profile"])
    examples = repository.get("route_contract_examples")
    if isinstance(examples, list):
        compacted["route_contract_examples"] = [
            _compact_route(example)
            for example in examples[:24]
            if isinstance(example, dict)
        ]
    return {key: value for key, value in compacted.items() if value not in (None, "", [], {})}


def _compact_project_analysis(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    compacted = {
        "version": value.get("version"),
        "analysis_mode": value.get("analysis_mode"),
        "review": value.get("review"),
        "relationship_guidance": value.get("relationship_guidance"),
        "route_count": value.get("route_count"),
        "dom_target_count": value.get("dom_target_count"),
    }
    modules = value.get("modules")
    if isinstance(modules, list):
        compacted["modules"] = [
            _compact_analysis_module(module)
            for module in modules[:16]
            if isinstance(module, dict)
        ]
    relationships = value.get("relationships")
    if isinstance(relationships, list):
        compacted["relationships"] = [
            _compact_analysis_relationship(item)
            for item in relationships[:32]
            if isinstance(item, dict)
        ]
    return {key: item for key, item in compacted.items() if item not in (None, "", [], {})}


def _compact_analysis_module(module: dict[str, Any]) -> dict[str, Any]:
    routes = module.get("routes")
    entrypoints = module.get("entrypoint_candidates")
    return {
        "id": module.get("id"),
        "name": module.get("name"),
        "domain": module.get("domain"),
        "route_count": module.get("route_count"),
        "scope_boundary": _trim_text(module.get("scope_boundary"), 260),
        "related_domains": module.get("related_domains"),
        "entrypoint_candidates": [
            _compact_analysis_route(route)
            for route in (entrypoints or [])[:6]
            if isinstance(route, dict)
        ],
        "routes": [
            _compact_analysis_route(route)
            for route in (routes or [])[:8]
            if isinstance(route, dict)
        ],
        "evidence": [
            _trim_text(item, 220)
            for item in (module.get("evidence") or [])[:6]
            if isinstance(item, str)
        ],
        "review_status": module.get("review_status"),
    }


def _compact_analysis_route(route: dict[str, Any]) -> dict[str, Any]:
    compacted = _compact_route(route)
    for key in ["role", "produces", "consumes", "related_domains", "request_body_fields"]:
        value = route.get(key)
        if value not in (None, "", [], {}):
            compacted[key] = value
    return compacted


def _compact_analysis_relationship(item: dict[str, Any]) -> dict[str, Any]:
    from_route = item.get("from_route") if isinstance(item.get("from_route"), dict) else {}
    to_route = item.get("to_route") if isinstance(item.get("to_route"), dict) else {}
    return {
        "type": item.get("type"),
        "variable": item.get("variable"),
        "from_route": _compact_route(from_route),
        "to_route": _compact_route(to_route),
        "from_module": item.get("from_module"),
        "to_module": item.get("to_module"),
        "confidence": item.get("confidence"),
        "confirmed": item.get("confirmed"),
        "reason": _trim_text(item.get("reason"), 220),
        "evidence": [
            _trim_text(evidence, 220)
            for evidence in (item.get("evidence") or [])[:4]
            if isinstance(evidence, str)
        ],
    }


def _compact_knowledge_graph(graph: dict[str, Any]) -> dict[str, Any]:
    modules = graph.get("modules")
    relationships = graph.get("relationships")
    compacted = {
        "version": graph.get("version"),
        "review": graph.get("review"),
        "summary": graph.get("summary"),
        "generation_policy": graph.get("generation_policy"),
    }
    if isinstance(modules, list):
        compacted["modules"] = [
            _compact_knowledge_module(module)
            for module in modules[:12]
            if isinstance(module, dict)
        ]
    if isinstance(relationships, list):
        compacted["relationships"] = [
            _compact_knowledge_relationship(item)
            for item in relationships[:24]
            if isinstance(item, dict)
        ]
    return {key: value for key, value in compacted.items() if value not in (None, "", [], {})}


def _compact_knowledge_module(module: dict[str, Any]) -> dict[str, Any]:
    routes = module.get("routes")
    return {
        "id": module.get("id"),
        "name": module.get("name"),
        "domain": module.get("domain"),
        "repository_kind": module.get("repository_kind"),
        "review_status": module.get("review_status"),
        "scope_boundary": _trim_text(module.get("scope_boundary"), 260),
        "related_domains": module.get("related_domains"),
        "entrypoint_route_ids": module.get("entrypoint_route_ids"),
        "routes": [
            _compact_knowledge_route(route)
            for route in (routes or [])[:8]
            if isinstance(route, dict)
        ],
        "evidence": [
            _trim_text(item, 220)
            for item in (module.get("evidence") or [])[:4]
            if isinstance(item, str)
        ],
    }


def _compact_knowledge_route(route: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": route.get("id"),
        "method": route.get("method"),
        "path": route.get("path"),
        "summary": _trim_text(route.get("summary"), 160),
        "source": _trim_text(route.get("source"), 180),
        "role": route.get("role"),
        "produces": route.get("produces"),
        "consumes": route.get("consumes"),
        "related_domains": route.get("related_domains"),
        "applicable_scenarios": _string_list(route.get("applicable_scenarios"), 4, 160),
        "excluded_scenarios": _string_list(route.get("excluded_scenarios"), 4, 180),
        "review_status": route.get("review_status"),
    }


def _compact_knowledge_relationship(item: dict[str, Any]) -> dict[str, Any]:
    from_route = item.get("from_route") if isinstance(item.get("from_route"), dict) else {}
    to_route = item.get("to_route") if isinstance(item.get("to_route"), dict) else {}
    return {
        "id": item.get("id"),
        "type": item.get("type"),
        "variable": item.get("variable"),
        "from_route": _compact_route(from_route),
        "to_route": _compact_route(to_route),
        "confidence": item.get("confidence"),
        "confirmed": item.get("confirmed"),
        "reason": _trim_text(item.get("reason"), 220),
        "review_status": item.get("review_status"),
    }


def _compact_auth_profile(value: dict[str, Any]) -> dict[str, Any]:
    compacted = deepcopy(value)
    evidence = compacted.get("evidence")
    if isinstance(evidence, list):
        compacted["evidence"] = [
            _trim_text(item, 220)
            for item in evidence[:12]
            if isinstance(item, str)
        ]
    candidates = compacted.get("login_route_candidates")
    if isinstance(candidates, list):
        compacted["login_route_candidates"] = [
            _compact_route(candidate)
            for candidate in candidates[:16]
            if isinstance(candidate, dict)
        ]
    return compacted


def _compact_reference_documents(value: Any, *, max_content_chars: int) -> Any:
    if not isinstance(value, list):
        return value
    documents: list[dict[str, Any]] = []
    for document in value:
        if not isinstance(document, dict):
            continue
        compacted = deepcopy(document)
        compacted["content"] = _trim_text(compacted.get("content"), max_content_chars)
        documents.append(compacted)
    return documents


def _halve_compacted_routes(
    payload: dict[str, Any],
    *,
    min_limits: dict[str, int] | None = None,
) -> bool:
    """预算仍超限时按仓库边界继续缩短路由列表。"""
    reduced = False
    limits = min_limits or {
        "backend_repository_summary": 24,
        "frontend_repository_summary": 8,
    }
    for key, min_limit in limits.items():
        summary = payload.get(key)
        if not isinstance(summary, dict):
            continue
        routes = summary.get("routes")
        if not isinstance(routes, list) or len(routes) <= min_limit:
            continue
        summary["routes"] = routes[: max(min_limit, len(routes) // 2)]
        reduced = True
    return reduced


def _request_body_fields(request_body: dict[str, Any]) -> list[str]:
    schema = request_body.get("schema")
    return _schema_fields(schema)


def _request_body_required_fields(request_body: dict[str, Any]) -> list[str]:
    schema = request_body.get("schema")
    if not isinstance(schema, dict):
        return []
    required = schema.get("required")
    return [str(item) for item in required] if isinstance(required, list) else []


def _schema_fields(schema: Any) -> list[str]:
    if not isinstance(schema, dict):
        return []
    properties = schema.get("properties")
    if isinstance(properties, dict):
        return [str(field) for field in properties]
    items = schema.get("items")
    if isinstance(items, dict):
        return _schema_fields(items)
    return []


def _schema_type(schema: Any) -> Any:
    if not isinstance(schema, dict):
        return None
    return schema.get("type") or schema.get("java_type") or schema.get("$ref")


def _object_keys(value: Any, limit: int) -> list[str]:
    return [str(key) for key in list(value)[:limit]] if isinstance(value, dict) else []


def _payload_relevance_text(payload: dict[str, Any]) -> str:
    """提取用于路由裁剪排序的本次需求文本。

    这里只做通用关键词匹配，不沉淀任何被测业务词；引用文档内容限制长度，
    防止排序辅助本身把大文档再次复制进内存热点。
    """

    parts: list[str] = []
    for key in ("natural_language", "flow_entrypoint"):
        value = payload.get(key)
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, dict):
            parts.extend(str(item) for item in value.values() if isinstance(item, str))
    fixtures = payload.get("reference_fixtures")
    if isinstance(fixtures, dict):
        parts.extend(str(item) for item in fixtures.values() if isinstance(item, (str, int, float)))
        for value in fixtures.values():
            if isinstance(value, list):
                parts.extend(str(item) for item in value[:24])
    documents = payload.get("reference_documents")
    if isinstance(documents, list):
        for document in documents[:6]:
            if not isinstance(document, dict):
                continue
            for key in ("title", "path", "content"):
                value = document.get(key)
                if isinstance(value, str):
                    parts.append(value[:4_000])
    return "\n".join(parts)


def _prioritized_items(
    value: Any,
    limit: int,
    relevance_text: str,
    *,
    item_text: Any,
) -> list[Any]:
    if not isinstance(value, list):
        return []
    items = value[:]
    if limit <= 0:
        return []
    terms = _relevance_terms(relevance_text)
    if not terms:
        return items[:limit]
    scored = [
        (_relevance_score(item_text(item), terms), index, item)
        for index, item in enumerate(items)
    ]
    scored.sort(key=lambda entry: (-entry[0], entry[1]))
    return [item for _, _, item in scored[:limit]]


def _relevance_terms(text: str) -> set[str]:
    lowered = text.lower()
    terms = {item for item in re.findall(r"[a-z0-9_/-]{2,}", lowered)}
    for segment in re.findall(r"[\u4e00-\u9fff]{2,}", lowered):
        max_window = min(6, len(segment))
        for size in range(2, max_window + 1):
            terms.update(segment[index : index + size] for index in range(len(segment) - size + 1))
    return {term for term in terms if len(term) >= 2}


def _relevance_score(text: str, terms: set[str]) -> int:
    lowered = text.lower()
    return sum(1 for term in terms if term in lowered)


def _route_relevance_text(route: Any) -> str:
    if not isinstance(route, dict):
        return ""
    parts = [
        route.get("method"),
        route.get("path"),
        route.get("summary"),
        route.get("description"),
        route.get("handler"),
        route.get("source"),
    ]
    for key in ("tags", "parameters"):
        value = route.get(key)
        if isinstance(value, list):
            parts.extend(json.dumps(item, ensure_ascii=False) for item in value[:16])
    for key in ("request_body", "responses"):
        value = route.get(key)
        if isinstance(value, (dict, list)):
            parts.append(json.dumps(value, ensure_ascii=False)[:4_000])
    return "\n".join(str(item) for item in parts if item not in (None, "", [], {}))


def _dom_target_relevance_text(target: Any) -> str:
    if not isinstance(target, dict):
        return ""
    return "\n".join(
        str(target.get(key))
        for key in ("kind", "value", "source", "hint")
        if target.get(key) not in (None, "")
    )


def _string_list(value: Any, limit: int, max_chars: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_trim_text(item, max_chars) for item in value[:limit] if isinstance(item, str)]


def _bounded_value(
    value: Any,
    *,
    max_string_chars: int,
    max_list_items: int,
    max_object_items: int,
) -> Any:
    if isinstance(value, str):
        return _trim_text(value, max_string_chars)
    if isinstance(value, list):
        return [
            _bounded_value(
                item,
                max_string_chars=max_string_chars,
                max_list_items=max_list_items,
                max_object_items=max_object_items,
            )
            for item in value[:max_list_items]
        ]
    if isinstance(value, dict):
        return {
            str(key): _bounded_value(
                child,
                max_string_chars=max_string_chars,
                max_list_items=max_list_items,
                max_object_items=max_object_items,
            )
            for key, child in list(value.items())[:max_object_items]
        }
    return value


def _trim_text(value: Any, max_chars: int) -> Any:
    if not isinstance(value, str) or len(value) <= max_chars:
        return value
    return f"{value[:max_chars]}{TRUNCATED_SUFFIX}"


def _json_chars(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False))
