from __future__ import annotations

from dataclasses import replace
import re
from typing import Any

from app.services.api_flow_variables import placeholders_in_value
from app.services.ai_case_generator import GeneratedCase, GeneratedStep

PRODUCER_ROUTE_KEYWORDS = (
    "page",
    "list",
    "search",
    "options",
    "detail",
    "home",
    "preview",
    "create",
    "分页",
    "列表",
    "搜索",
    "查询",
    "选项",
    "详情",
    "首页",
    "预检",
    "创建",
)


def annotate_api_flow_diagnostics(
    generated: GeneratedCase,
    routes: list[dict[str, Any]],
) -> GeneratedCase:
    """给生成结果补充接口参数链路诊断，不替模型硬造请求。

    这里不直接插入业务步骤，避免在后处理里猜错流程；它把“缺少上游生产者”
    写入步骤数据，让下一轮生成 prompt/agent 能据此补搜索、列表、详情或预检接口。
    """

    produced_variables: set[str] = set()
    next_steps: list[GeneratedStep] = []
    diagnostics: list[dict[str, Any]] = []

    for step in generated.steps:
        data = dict(step.data or {})
        if step.action == "api_request":
            step_diagnostics = _diagnostics_for_step(step, data, produced_variables, routes)
            if step_diagnostics:
                _merge_diagnostics(data, step_diagnostics)
                diagnostics.extend(
                    {
                        "step_label": step.label,
                        **item,
                    }
                    for item in step_diagnostics
                )
        produced_variables.update(_extract_variables(data.get("extract")))
        next_steps.append(replace(step, data=data if data else step.data))

    if not diagnostics:
        return generated

    context = dict(generated.code_context or {})
    context["api_flow_diagnostics"] = {
        "missing_upstream_step_count": len(
            [item for item in diagnostics if item.get("type") == "missing_upstream_step"]
        ),
        "items": diagnostics[:50],
    }
    return replace(generated, steps=next_steps, code_context=context)


def _diagnostics_for_step(
    step: GeneratedStep,
    data: dict[str, Any],
    produced_variables: set[str],
    routes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    placeholder_variables = (
        placeholders_in_value(step.target_url)
        | placeholders_in_value(data.get("headers"))
        | placeholders_in_value(data.get("body"))
    )
    for variable in sorted(placeholder_variables - produced_variables):
        if _is_external_fixture_variable(variable):
            diagnostics.append(
                {
                    "type": "unresolved_external_fixture",
                    "variable": variable,
                    "location": _placeholder_location(variable, step, data),
                    "reason": "该变量属于外部测试数据，不能由接口链路自动推导。",
                    "needed_evidence": "请补充真实请求样例或测试夹具字段。",
                }
            )
            continue
        candidates = _candidate_producer_routes(variable, routes, step)
        diagnostics.append(
            {
                "type": "missing_upstream_step",
                "variable": variable,
                "location": _placeholder_location(variable, step, data),
                "reason": "关键接口参数没有前置响应 extract 生产者，应先补上游查询、搜索、详情或创建接口。",
                "candidate_routes": candidates,
            }
        )

    for variable, literal in _hardcoded_path_parameters(step.target_url, data):
        normalized = _variable_name(variable)
        if normalized in produced_variables or _has_explicit_fixture_link(data, variable, literal):
            continue
        candidates = _candidate_producer_routes(normalized, routes, step)
        diagnostics.append(
            {
                "type": "missing_upstream_step",
                "variable": normalized,
                "literal_value": literal,
                "location": "target_url",
                "reason": "路径参数使用了硬编码长 ID，但没有前置接口证明该 ID 的来源。",
                "candidate_routes": candidates,
            }
        )

    return diagnostics


def _merge_diagnostics(data: dict[str, Any], diagnostics: list[dict[str, Any]]) -> None:
    unresolved = list(data.get("unresolved_parameters") or [])
    missing_steps = list(data.get("missing_upstream_steps") or [])
    unresolved_keys = {_diagnostic_key(item) for item in unresolved if isinstance(item, dict)}
    missing_keys = {_diagnostic_key(item) for item in missing_steps if isinstance(item, dict)}

    for item in diagnostics:
        if item["type"] == "missing_upstream_step":
            if _diagnostic_key(item) not in missing_keys:
                missing_steps.append(item)
                missing_keys.add(_diagnostic_key(item))
        if _diagnostic_key(item) not in unresolved_keys:
            unresolved.append(item)
            unresolved_keys.add(_diagnostic_key(item))

    if unresolved:
        data["unresolved_parameters"] = unresolved
    if missing_steps:
        data["missing_upstream_steps"] = missing_steps


def _diagnostic_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(item.get("type") or ""),
        str(item.get("variable") or item.get("name") or ""),
        str(item.get("location") or ""),
    )


def _extract_variables(extract: Any) -> set[str]:
    if isinstance(extract, dict):
        return {str(key) for key in extract if str(key).strip()}
    if isinstance(extract, list):
        variables: set[str] = set()
        for item in extract:
            if isinstance(item, dict):
                name = item.get("name") or item.get("variable")
                if name:
                    variables.add(str(name))
        return variables
    return set()


def _hardcoded_path_parameters(
    target_url: str | None,
    data: dict[str, Any],
) -> list[tuple[str, str]]:
    template = str(data.get("route_path_template") or data.get("document_path_template") or "")
    target = str(target_url or "")
    if not template or not target:
        return []

    template_parts = [part for part in template.split("/") if part]
    target_path = target.split("?", 1)[0]
    target_parts = [part for part in target_path.split("/") if part]
    if target_parts and target_parts[0] == "customer":
        target_parts = target_parts[1:]

    pairs: list[tuple[str, str]] = []
    for index, template_part in enumerate(template_parts):
        match = re.fullmatch(r"\{([^/{}]+)\}", template_part)
        if not match or index >= len(target_parts):
            continue
        literal = target_parts[index]
        if _looks_like_hardcoded_id(literal):
            pairs.append((match.group(1), literal))
    return pairs


def _looks_like_hardcoded_id(value: str) -> bool:
    return bool(re.fullmatch(r"\d{6,}", value))


def _is_external_fixture_variable(variable: str) -> bool:
    lower = variable.lower()
    return any(token in lower for token in ["payload", "fixture", "test_data", "mock"])


def _placeholder_location(variable: str, step: GeneratedStep, data: dict[str, Any]) -> str:
    if variable in placeholders_in_value(step.target_url):
        return "target_url"
    if variable in placeholders_in_value(data.get("headers")):
        return "headers"
    if variable in placeholders_in_value(data.get("body")):
        return "body"
    return "unknown"


def _has_explicit_fixture_link(data: dict[str, Any], variable: str, literal: str) -> bool:
    links = data.get("parameter_links")
    if not isinstance(links, list):
        return False
    names = {variable, _variable_name(variable), literal}
    for item in links:
        if not isinstance(item, dict):
            continue
        text = " ".join(str(value) for value in item.values())
        if not any(name in text for name in names):
            continue
        return any(token in text for token in ["固定测试夹具", "显式测试夹具", "explicit_fixture"])
    return False


def _candidate_producer_routes(
    variable: str,
    routes: list[dict[str, Any]],
    consumer_step: GeneratedStep,
) -> list[dict[str, Any]]:
    terms = _variable_terms(variable)
    ranked: list[tuple[int, dict[str, Any]]] = []
    consumer_template = str((consumer_step.data or {}).get("route_path_template") or "")
    for route in routes:
        route_path = str(route.get("path") or "")
        if route_path == consumer_template:
            continue
        searchable = _route_search_text(route)
        score = sum(3 for term in terms if term and term in searchable)
        if score <= 0:
            continue
        if any(keyword in searchable for keyword in PRODUCER_ROUTE_KEYWORDS):
            score += 4
        ranked.append((score, route))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [_route_candidate_payload(route) for _score, route in ranked[:5]]


def _variable_terms(variable: str) -> list[str]:
    base = _variable_name(variable)
    raw_parts = re.split(r"[_\-.]+", base.lower())
    terms = [part for part in raw_parts if part and part not in _VARIABLE_TERM_STOPWORDS]

    compact = base.replace("_", "")
    if compact and compact not in _VARIABLE_TERM_STOPWORDS:
        terms.append(compact)

    without_id = re.sub(r"(?:_?ids?|_?id)$", "", base)
    if without_id and without_id != base:
        terms.extend(part for part in without_id.split("_") if part)
        terms.append(without_id.replace("_", ""))

    for term in list(terms):
        terms.extend(_english_plural_variants(term))
    return list(dict.fromkeys(term for term in terms if term and term not in _VARIABLE_TERM_STOPWORDS))


_VARIABLE_TERM_STOPWORDS = {
    "id",
    "ids",
    "no",
    "num",
    "number",
    "code",
    "key",
    "value",
    "type",
}


def _english_plural_variants(term: str) -> list[str]:
    if not re.fullmatch(r"[a-z][a-z0-9]*", term):
        return []
    if len(term) <= 3:
        return []
    if term.endswith("ies"):
        return [term[:-3] + "y"]
    if term.endswith("s"):
        return [term[:-1]]
    return [term + "s"]


def _variable_name(variable: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", variable)
    value = value.replace("-", "_").replace(".", "_")
    return value.lower()


def _route_search_text(route: dict[str, Any]) -> str:
    values = [
        route.get("method"),
        route.get("path"),
        route.get("summary"),
        route.get("log"),
        route.get("handler"),
        route.get("source"),
    ]
    return " ".join(str(value or "") for value in values).lower()


def _route_candidate_payload(route: dict[str, Any]) -> dict[str, Any]:
    return {
        "method": route.get("method"),
        "path": route.get("path"),
        "summary": route.get("summary") or route.get("log"),
        "source": route.get("source"),
    }
