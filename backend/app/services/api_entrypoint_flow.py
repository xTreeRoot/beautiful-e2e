from __future__ import annotations

from dataclasses import replace
import re
from typing import Any

from app.services.api_route_matching import target_url_with_query
from app.services.case_generation_types import GeneratedCase, GeneratedStep
from app.services.flow_entrypoint import (
    DISCOVERY_ENTRYPOINT_TOKENS,
    dynamic_entity_discovery_required,
    entrypoint_terms,
    flow_entrypoint_from_prompt,
)
from app.services.reference_fixtures import best_reference_search_term, extract_reference_fixtures

PRODUCER_ROUTE_TOKENS = (
    "page",
    "list",
    "search",
    "query",
    "分页",
    "列表",
    "搜索",
    "查询",
)

def enforce_api_entrypoint_flow(
    generated: GeneratedCase,
    *,
    prompt: str,
    routes: list[dict[str, Any]],
    reference_documents: list[dict[str, Any]] | None = None,
) -> GeneratedCase:
    """修正显式入口和动态实体发现链路。

    供应商可能同时看到“接口地图里的固定 ID”和“用户要求从分页真实查询开始”。
    这里只在用户明确要求动态发现或显式入口时介入：入口接口必须排在首位，
    下游硬编码业务 ID 要改为由上游响应 extract 生产的变量。
    """

    entrypoint = flow_entrypoint_from_prompt(prompt)
    dynamic_required = dynamic_entity_discovery_required(
        prompt,
        raw_text=str(entrypoint.get("raw_text") or ""),
    )
    if not entrypoint.get("explicit") and not dynamic_required:
        return generated

    reference_fixtures = extract_reference_fixtures(reference_documents or [])
    steps = list(generated.steps)
    changes: list[dict[str, Any]] = []

    if entrypoint.get("explicit"):
        steps, entrypoint_changes = _ensure_entrypoint_first(
            steps,
            raw_text=str(entrypoint.get("raw_text") or ""),
            routes=routes,
            reference_fixtures=reference_fixtures,
        )
        changes.extend(entrypoint_changes)

    if dynamic_required:
        steps, link_changes = _link_dynamic_path_ids(steps)
        changes.extend(link_changes)

    context = dict(generated.code_context or {})
    context["api_dynamic_discovery_policy"] = {
        "entrypoint": entrypoint,
        "dynamic_entity_discovery_required": dynamic_required,
        "rule": (
            "当用户要求从查询、分页、列表或搜索入口真实发现业务实体时，"
            "文档固定 ID 只能作为候选或断言，下游参数必须绑定前置响应 extract。"
        ),
    }
    if changes:
        context["api_entrypoint_flow_enforcement"] = {
            "entrypoint": entrypoint,
            "dynamic_entity_discovery_required": dynamic_required,
            "items": changes[:80],
        }
    return replace(generated, steps=steps, code_context=context)


def _ensure_entrypoint_first(
    steps: list[GeneratedStep],
    *,
    raw_text: str,
    routes: list[dict[str, Any]],
    reference_fixtures: dict[str, Any],
) -> tuple[list[GeneratedStep], list[dict[str, Any]]]:
    first_api_index = _first_api_index(steps)
    if first_api_index is None or not raw_text:
        return steps, []

    matched_index = _entrypoint_step_index(steps, raw_text)
    if matched_index == first_api_index:
        return steps, []

    next_steps = list(steps)
    if matched_index is not None:
        step = next_steps.pop(matched_index)
        insert_at = first_api_index if matched_index > first_api_index else first_api_index - 1
        next_steps.insert(insert_at, step)
        return next_steps, [
            {
                "type": "entrypoint_reordered",
                "entrypoint": raw_text,
                "step_label": step.label,
                "reason": "用户显式要求该入口先执行，已把已有入口步骤移到第一个接口步骤位置。",
            }
        ]

    route = _best_route_for_entrypoint(raw_text, routes)
    if route is None:
        next_steps[first_api_index] = _annotate_missing_entrypoint(
            next_steps[first_api_index],
            raw_text,
            routes,
        )
        return next_steps, [
            {
                "type": "entrypoint_missing_route",
                "entrypoint": raw_text,
                "reason": "没有在真实路由目录中找到足够可信的入口接口，已把候选缺口写入首个接口步骤。",
                "candidate_routes": _candidate_routes(raw_text, routes),
            }
        ]

    entry_step = _entrypoint_route_step(
        route,
        raw_text=raw_text,
        gateway_prefix=_gateway_prefix_from_steps(steps),
        reference_fixtures=reference_fixtures,
    )
    next_steps.insert(first_api_index, entry_step)
    return next_steps, [
        {
            "type": "entrypoint_inserted",
            "entrypoint": raw_text,
            "step_label": entry_step.label,
            "target_url": entry_step.target_url,
            "route_source": (entry_step.data or {}).get("route_source"),
            "reason": "首个接口没有实现用户指定入口，已按真实路由目录插入入口发现接口。",
        }
    ]


def _link_dynamic_path_ids(steps: list[GeneratedStep]) -> tuple[list[GeneratedStep], list[dict[str, Any]]]:
    next_steps = list(steps)
    changes: list[dict[str, Any]] = []
    for index, step in enumerate(list(next_steps)):
        if step.action != "api_request":
            continue
        data = dict(step.data or {})
        pairs = _hardcoded_path_parameters(step.target_url, data)
        if not pairs:
            continue

        target_url = step.target_url or ""
        changed = False
        for variable, literal in pairs:
            if _previous_step_extracting(variable, next_steps[:index]) is not None:
                continue
            producer_index = _previous_dynamic_producer_index(next_steps[:index], variable)
            if producer_index is None:
                continue

            producer = next_steps[producer_index]
            producer_data = dict(producer.data or {})
            json_path = _jsonpath_for_variable(producer_data, variable)
            producer_extract = dict(producer_data.get("extract") or {})
            producer_extract[variable] = json_path
            producer_data["extract"] = producer_extract
            producer_data["produces_variables"] = sorted(producer_extract)
            producer_data["dynamic_discovery_producer"] = True
            next_steps[producer_index] = replace(producer, data=producer_data)

            target_url = _replace_path_literal(target_url, literal, f"{{{{{variable}}}}}")
            _merge_parameter_link(data, variable, producer, json_path)
            _remove_superseded_fixture_links(data, variable, literal)
            changed = True
            changes.append(
                {
                    "type": "dynamic_parameter_linked",
                    "variable": variable,
                    "from_step_label": producer.label,
                    "to_step_label": step.label,
                    "from_json_path": json_path,
                    "literal_replaced": literal,
                    "reason": "用户要求真实查询发现实体，已把下游硬编码 ID 改为上游响应变量。",
                }
            )

        if changed:
            data["dynamic_discovery_consumer"] = True
            data["route_contract_enforced"] = True
            next_steps[index] = replace(step, target_url=target_url, data=data)

    return next_steps, changes


def _entrypoint_step_index(steps: list[GeneratedStep], raw_text: str) -> int | None:
    for index, step in enumerate(steps):
        if step.action == "api_request" and _step_matches_entrypoint(step, raw_text):
            return index
    return None


def _step_matches_entrypoint(step: GeneratedStep, raw_text: str) -> bool:
    terms = set(entrypoint_terms(raw_text))
    if not terms:
        return False
    text = _step_search_text(step)
    score = sum(2 if term in DISCOVERY_ENTRYPOINT_TOKENS else 1 for term in terms if term in text)
    return score >= 4


def _best_route_for_entrypoint(raw_text: str, routes: list[dict[str, Any]]) -> dict[str, Any] | None:
    terms = set(entrypoint_terms(raw_text))
    wants_discovery = bool(terms & DISCOVERY_ENTRYPOINT_TOKENS)
    ranked: list[tuple[int, dict[str, Any]]] = []
    for route in routes:
        text = _route_search_text(route)
        score = sum(2 if term in DISCOVERY_ENTRYPOINT_TOKENS else 1 for term in terms if term in text)
        if wants_discovery and _looks_like_discovery_route(text):
            score += 5
        if wants_discovery and _route_requires_path_id(route):
            score -= 4
        if _looks_like_admin_or_merchant_route(text) and "管理" not in raw_text and "商户" not in raw_text:
            score -= 5
        if score >= 4:
            ranked.append((score, route))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1]


def _entrypoint_route_step(
    route: dict[str, Any],
    *,
    raw_text: str,
    gateway_prefix: str,
    reference_fixtures: dict[str, Any],
) -> GeneratedStep:
    method = str(route.get("method") or "GET").upper()
    target_url = _with_gateway_prefix(gateway_prefix, str(route.get("path") or "/"))
    data: dict[str, Any] = {
        "method": method if method != "ANY" else "GET",
        "expected_status": 200,
        "route_source": route.get("source"),
        "route_summary": route.get("summary") or route.get("log"),
        "route_path_template": route.get("path"),
        "route_parameters": route.get("parameters"),
        "route_request_body": route.get("request_body"),
        "route_responses": route.get("responses"),
        "flow_reason": f"用户显式要求从「{raw_text}」开始，先用入口接口发现后续业务实体。",
        "entrypoint_enforced": True,
    }
    data = {key: value for key, value in data.items() if value not in (None, "", [], {})}

    body = _body_for_entrypoint_route(route, reference_fixtures)
    if body:
        data["body"] = body
    query = _query_for_entrypoint_route(route, reference_fixtures)
    if query:
        target_url = target_url_with_query(target_url, query)

    label = str(route.get("summary") or route.get("log") or route.get("handler") or raw_text)
    return GeneratedStep(
        kind="api",
        label=f"{raw_text}: {label}",
        action="api_request",
        target_url=target_url,
        expected="200",
        data=data,
    )


def _body_for_entrypoint_route(
    route: dict[str, Any],
    reference_fixtures: dict[str, Any],
) -> dict[str, Any]:
    request_body = route.get("request_body")
    if not isinstance(request_body, dict):
        return {}
    body = dict(request_body.get("example") or {}) if isinstance(request_body.get("example"), dict) else {}
    properties = _schema_properties(request_body)
    for field in properties:
        if field in body or not _is_search_name_field(field):
            continue
        fixture = best_reference_search_term(reference_fixtures, field=field, route=route)
        if fixture:
            body[field] = fixture["value"]
    return body


def _query_for_entrypoint_route(
    route: dict[str, Any],
    reference_fixtures: dict[str, Any],
) -> dict[str, Any]:
    parameters = route.get("parameters")
    if not isinstance(parameters, list):
        return {}
    query: dict[str, Any] = {}
    for parameter in parameters:
        if not isinstance(parameter, dict) or str(parameter.get("in") or "").lower() != "query":
            continue
        name = str(parameter.get("name") or "")
        if not name:
            continue
        if parameter.get("example") is not None:
            query[name] = parameter["example"]
        elif _is_search_name_field(name):
            fixture = best_reference_search_term(reference_fixtures, field=name, route=route)
            if fixture:
                query[name] = fixture["value"]
    return query


def _hardcoded_path_parameters(target_url: str | None, data: dict[str, Any]) -> list[tuple[str, str]]:
    template = str(data.get("route_path_template") or data.get("document_path_template") or "")
    target = str(target_url or "")
    if not template or not target:
        return []

    template_parts = [part for part in template.split("/") if part]
    target_parts = [part for part in target.split("?", 1)[0].split("/") if part]
    if target_parts and target_parts[0] in {"customer", "merchant", "admin"}:
        target_parts = target_parts[1:]

    pairs: list[tuple[str, str]] = []
    for index, template_part in enumerate(template_parts):
        match = re.fullmatch(r"\{([^/{}]+)\}", template_part)
        if not match or index >= len(target_parts):
            continue
        literal = target_parts[index]
        if re.fullmatch(r"\d{6,}", literal):
            pairs.append((match.group(1), literal))
    return pairs


def _previous_dynamic_producer_index(steps: list[GeneratedStep], variable: str) -> int | None:
    best: tuple[int, int] | None = None
    for index, step in enumerate(steps):
        if step.action != "api_request":
            continue
        text = _step_search_text(step)
        if not _looks_like_discovery_route(text):
            continue
        score = _producer_score(variable, text)
        if score <= 0:
            continue
        if best is None or score >= best[0]:
            best = (score, index)
    return best[1] if best else None


def _producer_score(variable: str, text: str) -> int:
    variable_terms = _variable_terms(variable)
    score = sum(2 for term in variable_terms if term in text)
    if _looks_like_discovery_route(text):
        score += 2
    return score


def _variable_terms(variable: str) -> list[str]:
    words = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)|\d+", variable)
    terms = [word.lower() for word in words if word.lower() != "id"]
    return list(dict.fromkeys(term for term in terms if term))


def _jsonpath_for_variable(data: dict[str, Any], variable: str) -> str:
    route_text = _data_route_text(data)
    if any(token in route_text for token in ["page", "list", "分页", "列表"]):
        return f"$.data.list[0].{variable}"
    fields = _response_fields(data.get("route_responses"))
    if variable in fields:
        return f"$.data.{variable}"
    return f"$.data.{variable}"


def _response_fields(responses: Any) -> set[str]:
    fields: set[str] = set()
    if not isinstance(responses, list):
        return fields
    for response in responses:
        if isinstance(response, dict) and isinstance(response.get("fields"), list):
            fields.update(str(item) for item in response["fields"])
    return fields


def _previous_step_extracting(variable: str, previous_steps: list[GeneratedStep]) -> GeneratedStep | None:
    for step in reversed(previous_steps):
        extract = (step.data or {}).get("extract")
        if isinstance(extract, dict) and variable in extract:
            return step
    return None


def _merge_parameter_link(
    data: dict[str, Any],
    variable: str,
    producer: GeneratedStep,
    json_path: str,
) -> None:
    link = {
        "variable": variable,
        "from_step_label": producer.label,
        "source": "previous_response",
        "binding": "target_url",
        "json_path": json_path,
        "required": True,
        "reason": "该路径参数来自用户指定的入口发现接口响应。",
    }
    for field in ["parameter_links", "depends_on"]:
        current = [item for item in data.get(field, []) if isinstance(item, dict)]
        exists = any(
            str(item.get("variable")) == variable and item.get("from_step_label") == producer.label
            for item in current
        )
        if not exists:
            current.append(link)
        data[field] = current


def _remove_superseded_fixture_links(data: dict[str, Any], variable: str, literal: str) -> None:
    links = data.get("parameter_links")
    if not isinstance(links, list):
        return
    data["parameter_links"] = [
        item
        for item in links
        if not (
            isinstance(item, dict)
            and str(item.get("variable")) == variable
            and str(item.get("value")) == literal
            and "explicit_fixture" in str(item.get("reason") or "")
        )
    ]


def _replace_path_literal(target_url: str, literal: str, placeholder: str) -> str:
    return re.sub(rf"(?<=/){re.escape(literal)}(?=/|$|\?)", placeholder, target_url, count=1)


def _annotate_missing_entrypoint(
    step: GeneratedStep,
    raw_text: str,
    routes: list[dict[str, Any]],
) -> GeneratedStep:
    data = dict(step.data or {})
    missing = [item for item in data.get("missing_upstream_steps", []) if isinstance(item, dict)]
    missing.append(
        {
            "type": "missing_entrypoint_step",
            "entrypoint": raw_text,
            "reason": "用户显式要求该入口先执行，但生成结果没有找到对应真实接口。",
            "candidate_routes": _candidate_routes(raw_text, routes),
        }
    )
    data["missing_upstream_steps"] = missing
    return replace(step, data=data)


def _candidate_routes(raw_text: str, routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    terms = set(entrypoint_terms(raw_text))
    ranked: list[tuple[int, dict[str, Any]]] = []
    for route in routes:
        text = _route_search_text(route)
        score = sum(1 for term in terms if term in text)
        if score:
            ranked.append((score, route))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "method": route.get("method"),
            "path": route.get("path"),
            "summary": route.get("summary") or route.get("log"),
            "source": route.get("source"),
        }
        for _score, route in ranked[:8]
    ]


def _first_api_index(steps: list[GeneratedStep]) -> int | None:
    for index, step in enumerate(steps):
        if step.action == "api_request":
            return index
    return None


def _gateway_prefix_from_steps(steps: list[GeneratedStep]) -> str:
    for step in steps:
        target = str(step.target_url or "")
        for prefix in ["/customer", "/merchant", "/admin"]:
            if target.startswith(f"{prefix}/api/"):
                return prefix
    return ""


def _with_gateway_prefix(prefix: str, path: str) -> str:
    if not prefix or path.startswith(f"{prefix}/"):
        return path
    if path.startswith("/api/") or path.startswith("/merchant/"):
        return f"{prefix}{path}"
    return path


def _route_requires_path_id(route: dict[str, Any]) -> bool:
    path = str(route.get("path") or "")
    return bool(re.search(r"\{[^/{}]*id[^/{}]*\}", path, flags=re.I))


def _looks_like_discovery_route(text: str) -> bool:
    return any(token in text for token in PRODUCER_ROUTE_TOKENS)


def _looks_like_admin_or_merchant_route(text: str) -> bool:
    return any(token in text for token in ["admin", "merchant", "管理端", "商户"])


def _is_search_name_field(field: str) -> bool:
    normalized = field.replace("_", "").lower()
    return bool(
        normalized in {"name", "title", "displaytitle", "keyword", "query", "searchtext"}
        or normalized.endswith("name")
        or normalized.endswith("title")
    )


def _schema_properties(request_body: dict[str, Any]) -> dict[str, Any]:
    schema = request_body.get("schema")
    if not isinstance(schema, dict):
        return {}
    properties = schema.get("properties")
    return properties if isinstance(properties, dict) else {}


def _route_search_text(route: dict[str, Any]) -> str:
    values = [
        route.get("method"),
        route.get("path"),
        route.get("summary"),
        route.get("log"),
        route.get("description"),
        route.get("handler"),
        route.get("source"),
        route.get("tags"),
        route.get("parameters"),
        route.get("request_body"),
    ]
    return " ".join(str(value or "") for value in values).lower()


def _step_search_text(step: GeneratedStep) -> str:
    data = step.data or {}
    values = [
        step.label,
        step.target_url,
        data.get("route_summary"),
        data.get("route_path_template"),
        data.get("document_path_template"),
        data.get("route_source"),
        data.get("route_request_body"),
    ]
    return " ".join(str(value or "") for value in values).lower()


def _data_route_text(data: dict[str, Any]) -> str:
    values = [
        data.get("route_summary"),
        data.get("route_path_template"),
        data.get("route_source"),
        data.get("route_responses"),
    ]
    return " ".join(str(value or "") for value in values).lower()
