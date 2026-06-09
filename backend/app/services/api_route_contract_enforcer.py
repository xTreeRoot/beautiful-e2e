from __future__ import annotations

from dataclasses import replace
import re
from typing import Any

from app.services.case_generation_types import GeneratedCase, GeneratedStep
from app.services.api_route_matching import (
    matching_route,
    query_params_from_url,
    route_matches_target,
    target_url_for_route,
    target_url_with_query,
)
from app.services.reference_fixtures import (
    best_reference_search_term,
    compact_reference_fixtures,
    extract_reference_fixtures,
    fixture_parameter_links_for_target,
)


BODY_FIELD_ALIASES = {
    "current": ("page", "pageNo", "pageNum"),
    "pageSize": ("limit", "size"),
    "size": ("limit", "pageSize"),
    "keyword": ("name", "title", "keyword"),
    "keywords": ("name", "title", "keyword"),
    "query": ("name", "title", "keyword"),
}

def enforce_api_route_contracts(
    generated: GeneratedCase,
    routes: list[dict[str, Any]],
    reference_documents: list[dict[str, Any]] | None = None,
    *,
    allow_fixture_parameter_links: bool = True,
) -> GeneratedCase:
    """按真实路由契约修正模型返回的接口步骤。

    供应商可能读到了正确 URL，却把 Spring DTO 字段改成通用分页字段。
    后处理只依据已扫描出的路由和请求体 schema 做窄范围校正，不新增业务流程。
    """

    if not routes:
        return generated

    reference_fixtures = extract_reference_fixtures(reference_documents or [])
    compact_fixtures = compact_reference_fixtures(reference_fixtures)
    next_steps: list[GeneratedStep] = []
    corrections: list[dict[str, Any]] = []
    changed = False
    for step in generated.steps:
        if step.action != "api_request":
            next_steps.append(step)
            continue
        data = dict(step.data or {})
        route = matching_route(step, data, routes)
        if not route:
            next_steps.append(step)
            continue

        next_target_url = step.target_url
        step_corrections: list[dict[str, Any]] = []
        if not route_matches_target(route, step.target_url):
            corrected_url = target_url_for_route(step.target_url or "", route)
            if corrected_url and corrected_url != step.target_url:
                next_target_url = corrected_url
                step_corrections.append(
                    {
                        "field": "target_url",
                        "from": step.target_url,
                        "to": corrected_url,
                        "reason": "生成 URL 未命中真实路由目录，已按最接近的项目路由纠正。",
                    }
                )

        _merge_route_contract(data, route)
        if allow_fixture_parameter_links:
            changed = _merge_fixture_parameter_links(data, step, reference_fixtures) or changed
        else:
            removed_fixture_links = _remove_fixture_parameter_links(data)
            if removed_fixture_links:
                changed = True
                step_corrections.append(
                    {
                        "field": "parameter_links",
                        "reason": (
                            "当前生成要求从上游查询真实发现实体，引用文档固定 ID "
                            "不能作为 required 参数来源。"
                        ),
                    }
                )
        route_method = str(route.get("method") or data.get("method") or "GET").upper()
        current_method = str(data.get("method") or "GET").upper()
        if route_method != current_method and route_method != "ANY":
            data["method"] = route_method
            step_corrections.append(
                {
                    "field": "method",
                    "from": current_method,
                    "to": route_method,
                    "reason": "生成结果与真实 Controller 路由方法不一致。",
                }
            )
        elif route_method == "ANY":
            data["method"] = current_method

        query_params = query_params_from_url(next_target_url or "")
        if data["method"] in {"GET", "DELETE"} and "body" in data:
            body_query_params, body_query_corrections = _body_as_query_params(
                data.get("body"),
                route,
            )
            if body_query_params:
                query_params = {**body_query_params, **query_params}
                step_corrections.extend(body_query_corrections)
            data.pop("body", None)
            step_corrections.append(
                {
                    "field": "body",
                    "reason": "真实路由是无请求体方法，已将可识别字段迁移到 query 或移除。",
                }
            )

        request_body = route.get("request_body")
        if isinstance(request_body, dict) and data["method"] in {"POST", "PUT", "PATCH"}:
            body_seed = _body_with_query_params(
                data.get("body"),
                query_params,
                route,
            )
            body, body_corrections = _body_for_route_schema(
                body_seed,
                request_body,
                route,
                reference_fixtures,
            )
            if body_corrections:
                data["body"] = body
                step_corrections.extend(body_corrections)
            elif data.get("body") is None and body is not None:
                data["body"] = body
        query_params, query_corrections = _query_params_for_route(
            query_params,
            route,
            data["method"],
        )
        if query_corrections:
            step_corrections.extend(query_corrections)
        next_target_url = target_url_with_query(next_target_url or "", query_params)

        if step_corrections:
            changed = True
            data["route_contract_enforced"] = True
            data["route_contract_corrections"] = step_corrections
            if compact_fixtures:
                data["reference_fixtures"] = compact_fixtures
            corrections.extend({"step_label": step.label, **item} for item in step_corrections)
        next_steps.append(replace(step, target_url=next_target_url, data=data))

    if not changed:
        return generated

    context = dict(generated.code_context or {})
    if corrections:
        context["api_route_contract_enforcement"] = {"items": corrections[:80]}
    return replace(generated, steps=next_steps, code_context=context)


def _merge_route_contract(data: dict[str, Any], route: dict[str, Any]) -> None:
    route_fields = {
        "source": "route_source",
        "summary": "route_summary",
        "log": "route_summary",
        "path": "route_path_template",
        "parameters": "route_parameters",
        "request_body": "route_request_body",
        "responses": "route_responses",
    }
    for route_key, data_key in route_fields.items():
        value = route.get(route_key)
        if value and not data.get(data_key):
            data[data_key] = value


def _query_parameters(route: dict[str, Any]) -> list[dict[str, Any]]:
    parameters = route.get("parameters")
    if not isinstance(parameters, list):
        return []
    return [
        parameter
        for parameter in parameters
        if isinstance(parameter, dict) and str(parameter.get("in") or "").lower() == "query"
    ]


def _parameter_schema(name: str, parameters: list[dict[str, Any]]) -> dict[str, Any]:
    for parameter in parameters:
        if str(parameter.get("name") or "") != name:
            continue
        schema = parameter.get("schema")
        return schema if isinstance(schema, dict) else {}
    return {}


def _query_params_for_route(
    query_params: dict[str, Any],
    route: dict[str, Any],
    method: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    query_contract = _query_parameters(route)
    if not query_contract:
        if query_params and method in {"POST", "PUT", "PATCH"} and isinstance(route.get("request_body"), dict):
            return {}, [
                {
                    "field": "query",
                    "from": sorted(query_params),
                    "reason": "真实路由使用请求体契约，URL query 已迁移到 body 或移除。",
                }
            ]
        return query_params, []

    allowed = {str(item.get("name")) for item in query_contract if item.get("name")}
    next_query: dict[str, Any] = {}
    corrections: list[dict[str, Any]] = []
    dropped_fields: list[str] = []
    for key, value in query_params.items():
        target_key = _body_field_target(str(key), allowed)
        if target_key is None:
            dropped_fields.append(str(key))
            continue
        parameter_schema = _parameter_schema(target_key, query_contract)
        next_query[target_key] = _coerce_schema_value(value, parameter_schema)
        if target_key != key:
            corrections.append(
                {
                    "field": "query",
                    "from": key,
                    "to": target_key,
                    "reason": "生成 query 字段不在真实参数契约中，已映射到最接近字段。",
                }
            )

    for parameter in query_contract:
        name = str(parameter.get("name") or "")
        if not name or name in next_query or not parameter.get("required"):
            continue
        if "example" not in parameter:
            continue
        next_query[name] = parameter["example"]
        corrections.append(
            {
                "field": f"query.{name}",
                "to": parameter["example"],
                "reason": "真实 query 参数契约提供了必填示例，已补齐。",
            }
        )

    if dropped_fields:
        corrections.append(
            {
                "field": "query",
                "from": dropped_fields,
                "reason": "这些 query 字段不存在于真实接口参数契约中，已从 URL 移除。",
            }
        )
    return next_query, corrections


def _body_as_query_params(
    body: Any,
    route: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(body, dict):
        return {}, []
    query_contract = _query_parameters(route)
    if not query_contract:
        return {}, []
    allowed = {str(item.get("name")) for item in query_contract if item.get("name")}
    migrated: dict[str, Any] = {}
    corrections: list[dict[str, Any]] = []
    for key, value in body.items():
        target_key = _body_field_target(str(key), allowed)
        if target_key is None:
            continue
        migrated[target_key] = value
        corrections.append(
            {
                "field": f"body.{key}",
                "to": f"query.{target_key}",
                "reason": "真实 GET/DELETE 路由使用 query 参数，已从 body 迁移。",
            }
        )
    return migrated, corrections


def _body_with_query_params(
    body: Any,
    query_params: dict[str, Any],
    route: dict[str, Any],
) -> Any:
    if not query_params:
        return body
    route_query_names = {str(item.get("name")) for item in _query_parameters(route) if item.get("name")}
    movable = {key: value for key, value in query_params.items() if key not in route_query_names}
    if not movable:
        return body
    if isinstance(body, dict):
        return {**movable, **body}
    return movable


def _coerce_schema_value(value: Any, schema: Any) -> Any:
    if not isinstance(schema, dict) or not isinstance(value, str):
        return value
    schema_type = str(schema.get("type") or "").lower()
    if schema_type in {"integer", "int", "long"} and re.fullmatch(r"-?\d+", value):
        return int(value)
    if schema_type in {"number", "float", "double"} and re.fullmatch(r"-?\d+(?:\.\d+)?", value):
        return float(value)
    if schema_type == "boolean" and value.lower() in {"true", "false"}:
        return value.lower() == "true"
    return value


def _body_for_route_schema(
    body: Any,
    request_body: dict[str, Any],
    route: dict[str, Any],
    reference_fixtures: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    properties = _schema_properties(request_body)
    example = request_body.get("example") if isinstance(request_body.get("example"), dict) else {}
    if not properties:
        return (body if isinstance(body, dict) else example or None), []

    if not isinstance(body, dict):
        if example:
            return dict(example), [
                {
                    "field": "body",
                    "to": sorted(example),
                    "reason": "真实路由请求体提供了 DTO 示例，已补齐请求体。",
                }
            ]
        return None, []

    allowed = set(properties)
    next_body: dict[str, Any] = {}
    corrections: list[dict[str, Any]] = []
    dropped_fields: list[str] = []
    for key, value in body.items():
        target_key = _body_field_target(str(key), allowed)
        if target_key is None:
            dropped_fields.append(str(key))
            continue
        next_value, value_correction = _reference_fixture_body_value(
            target_key,
            value,
            route,
            reference_fixtures,
        )
        next_value = _coerce_schema_value(next_value, properties.get(target_key))
        next_body[target_key] = next_value
        if target_key != key:
            corrections.append(
                {
                    "field": "body",
                    "from": key,
                    "to": target_key,
                    "reason": "生成字段不在真实 DTO 中，已映射到最接近的 DTO 字段。",
                }
            )
        if value_correction:
            corrections.append(value_correction)

    required = set(_schema_required(request_body))
    for key, value in example.items():
        if key in allowed and key not in next_body and (key in required or key in {"page", "limit"}):
            next_body[key] = value
            corrections.append(
                {
                    "field": f"body.{key}",
                    "to": key,
                    "reason": "真实 DTO 示例提供了必填或分页默认值。",
                }
            )

    for key in allowed:
        if key in next_body or not _is_search_name_field(key) or not _route_looks_like_search(route):
            continue
        fixture = best_reference_search_term(reference_fixtures, field=key, route=route)
        if not fixture:
            continue
        next_body[key] = fixture["value"]
        corrections.append(
            {
                "field": f"body.{key}",
                "to": fixture["value"],
                "reason": "引用文档提供了精确业务名称，已补入搜索字段。",
                "source": fixture.get("source"),
            }
        )

    if dropped_fields:
        corrections.append(
            {
                "field": "body",
                "from": dropped_fields,
                "reason": "这些字段不存在于真实 DTO 请求体中，已从可执行 body 移除。",
            }
        )
    if next_body != body and not corrections:
        corrections.append({"field": "body", "reason": "请求体已按真实 DTO 字段顺序规整。"})
    return next_body, corrections


def _schema_properties(request_body: dict[str, Any]) -> dict[str, Any]:
    schema = request_body.get("schema")
    if not isinstance(schema, dict):
        return {}
    properties = schema.get("properties")
    return properties if isinstance(properties, dict) else {}


def _schema_required(request_body: dict[str, Any]) -> list[str]:
    schema = request_body.get("schema")
    if not isinstance(schema, dict):
        return []
    required = schema.get("required")
    return [str(item) for item in required] if isinstance(required, list) else []


def _body_field_target(field: str, allowed: set[str]) -> str | None:
    if field in allowed:
        return field
    for candidate in BODY_FIELD_ALIASES.get(field, ()):
        if candidate in allowed:
            return candidate
    if _is_search_name_field(field):
        for candidate in allowed:
            if _is_search_name_field(candidate):
                return candidate
    lowered_allowed = {item.lower(): item for item in allowed}
    return lowered_allowed.get(field.lower())


def _merge_fixture_parameter_links(
    data: dict[str, Any],
    step: GeneratedStep,
    reference_fixtures: dict[str, Any],
) -> bool:
    links = fixture_parameter_links_for_target(
        target_url=step.target_url,
        route_template=str(data.get("route_path_template") or data.get("document_path_template") or ""),
        fixtures=reference_fixtures,
    )
    if not links:
        return False
    current_links = [item for item in data.get("parameter_links", []) if isinstance(item, dict)]
    current_keys = {
        (str(item.get("variable")), str(item.get("value")), str(item.get("location")))
        for item in current_links
    }
    changed = False
    for link in links:
        key = (str(link.get("variable")), str(link.get("value")), str(link.get("location")))
        if key not in current_keys:
            current_links.append(link)
            current_keys.add(key)
            changed = True
    data["parameter_links"] = current_links
    return changed


def _remove_fixture_parameter_links(data: dict[str, Any]) -> int:
    links = data.get("parameter_links")
    if not isinstance(links, list):
        return 0
    next_links = [
        item
        for item in links
        if not (isinstance(item, dict) and "explicit_fixture" in str(item.get("reason") or ""))
    ]
    removed = len(links) - len(next_links)
    if next_links:
        data["parameter_links"] = next_links
    else:
        data.pop("parameter_links", None)
    return removed


def _reference_fixture_body_value(
    field: str,
    value: Any,
    route: dict[str, Any],
    reference_fixtures: dict[str, Any],
) -> tuple[Any, dict[str, Any] | None]:
    if not _is_search_name_field(field):
        return value, None
    fixture = best_reference_search_term(
        reference_fixtures,
        field=field,
        current_value=value,
        route=route,
    )
    if not fixture:
        return value, None
    replacement = fixture["value"]
    if replacement == value:
        return value, None
    return replacement, {
        "field": f"body.{field}",
        "from": value,
        "to": replacement,
        "reason": "引用文档提供了比短关键词更精确的业务名称。",
        "source": fixture.get("source"),
    }


def _is_search_name_field(field: str) -> bool:
    normalized = field.replace("_", "").lower()
    return bool(
        normalized in {"name", "title", "displaytitle", "keyword", "query", "searchtext"}
        or normalized.endswith("name")
        or normalized.endswith("title")
    )


def _route_looks_like_search(route: dict[str, Any]) -> bool:
    text = " ".join(
        str(route.get(key) or "")
        for key in ["path", "summary", "description", "handler", "source"]
    ).lower()
    return any(token in text for token in ["page", "list", "search", "query", "分页", "列表", "搜索", "查询"])
