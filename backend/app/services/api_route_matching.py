from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.services.case_generation_types import GeneratedStep

GATEWAY_PREFIXES = ("/customer", "/merchant", "/admin")


def matching_route(
    step: GeneratedStep,
    data: dict[str, Any],
    routes: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """按 URL 精确匹配优先，失败时用高阈值相似度寻找真实路由候选。

    近似匹配只作为模型写错相邻路径段时的后处理保护，不能在没有项目路由证据时
    自行创造接口。
    """

    target_path = strip_gateway_prefix(url_path(step.target_url or ""))
    if not target_path:
        return None
    step_method = str(data.get("method") or "").upper()
    candidates: list[dict[str, Any]] = []
    for route in routes:
        route_path = str(route.get("path") or "")
        normalized_route_path = strip_gateway_prefix(route_path)
        if target_path == normalized_route_path or route_template_matches(
            normalized_route_path,
            target_path,
        ):
            candidates.append(route)
    if not candidates:
        return _similar_route(step, data, routes, target_path)
    same_method = [
        route
        for route in candidates
        if str(route.get("method") or "").upper() in {step_method, "ANY"}
    ]
    return (same_method or candidates)[0]


def route_matches_target(route: dict[str, Any], target_url: str | None) -> bool:
    target_path = strip_gateway_prefix(url_path(target_url or ""))
    route_path = strip_gateway_prefix(str(route.get("path") or ""))
    return bool(
        target_path
        and route_path
        and (target_path == route_path or route_template_matches(route_path, target_path))
    )


def url_path(value: str) -> str:
    if not value:
        return ""
    parsed = urlsplit(value)
    path = parsed.path if parsed.scheme or parsed.netloc else value.split("?", 1)[0]
    return path if path.startswith("/") else f"/{path}"


def target_url_for_route(value: str, route: dict[str, Any]) -> str | None:
    route_path = str(route.get("path") or "").strip()
    if not route_path:
        return None
    original = urlsplit(value)
    original_path = url_path(value)
    materialized = _materialize_route_path(route_path, strip_gateway_prefix(original_path))
    gateway_prefix = _gateway_prefix(original_path)
    next_path = (
        f"{gateway_prefix}{materialized}"
        if gateway_prefix and materialized.startswith("/api/")
        else materialized
    )
    if original.scheme or original.netloc:
        return urlunsplit((original.scheme, original.netloc, next_path, original.query, original.fragment))
    return urlunsplit(("", "", next_path, original.query, original.fragment))


def target_url_with_query(value: str, query_params: dict[str, Any]) -> str:
    parsed = urlsplit(value)
    path = parsed.path if parsed.scheme or parsed.netloc else value.split("?", 1)[0]
    query = urlencode(
        [(key, "" if item is None else str(item)) for key, item in query_params.items()],
        doseq=True,
    )
    if parsed.scheme or parsed.netloc:
        return urlunsplit((parsed.scheme, parsed.netloc, path, query, parsed.fragment))
    return urlunsplit(("", "", path, query, parsed.fragment))


def query_params_from_url(value: str) -> dict[str, str]:
    parsed = urlsplit(value)
    return {key: item for key, item in parse_qsl(parsed.query, keep_blank_values=True)}


def strip_gateway_prefix(path: str) -> str:
    for prefix in GATEWAY_PREFIXES:
        if path.startswith(f"{prefix}/api/"):
            return path[len(prefix) :]
    return path


def route_template_matches(route_template: str, target_path: str) -> bool:
    pattern = "^" + re.sub(r"\\{[^/{}]+\\}", r"[^/]+", re.escape(route_template)) + "$"
    return bool(re.match(pattern, target_path))


def _similar_route(
    step: GeneratedStep,
    data: dict[str, Any],
    routes: list[dict[str, Any]],
    target_path: str,
) -> dict[str, Any] | None:
    step_method = str(data.get("method") or "").upper()
    ranked: list[tuple[int, dict[str, Any]]] = []
    for route in routes:
        route_path = strip_gateway_prefix(str(route.get("path") or ""))
        if not route_path:
            continue
        score = _path_similarity_score(target_path, route_path)
        score += _text_similarity_score(step, route)
        route_method = str(route.get("method") or "").upper()
        if route_method in {step_method, "ANY"}:
            score += 4
        if _route_family(target_path) and _route_family(target_path) == _route_family(route_path):
            score += 8
        if score >= 28:
            ranked.append((score, route))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1]


def _path_similarity_score(target_path: str, route_path: str) -> int:
    target_parts = [part for part in target_path.lower().split("/") if part]
    route_parts = [part for part in route_path.lower().split("/") if part]
    if not target_parts or not route_parts:
        return 0

    score = 0
    if len(target_parts) == len(route_parts):
        score += 8
    elif abs(len(target_parts) - len(route_parts)) <= 1:
        score += 3

    for index, route_part in enumerate(route_parts):
        if index >= len(target_parts):
            continue
        target_part = target_parts[index]
        if route_part == target_part:
            score += 4
        elif re.fullmatch(r"\{[^/{}]+\}", route_part):
            score += 2

    if target_parts[-1] == route_parts[-1]:
        score += 6
    score += min(len(set(target_parts) & set(route_parts)) * 2, 10)
    return score


def _text_similarity_score(step: GeneratedStep, route: dict[str, Any]) -> int:
    step_text = " ".join(
        str(value or "")
        for value in [step.label, step.target_url, (step.data or {}).get("route_summary")]
    )
    route_text = " ".join(
        str(route.get(key) or "")
        for key in ["path", "summary", "description", "log", "handler", "source"]
    )
    step_terms = set(_search_terms(step_text))
    route_terms = set(_search_terms(route_text))
    if not step_terms or not route_terms:
        return 0
    return min(len(step_terms & route_terms) * 2, 20)


def _search_terms(value: str) -> list[str]:
    terms = [item.lower() for item in re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}", value)]
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]+", value))
    terms.extend(chinese[index : index + 2] for index in range(max(len(chinese) - 1, 0)))
    return [term for term in terms if term not in {"api", "get", "post", "put", "delete"}]


def _route_family(path: str) -> str:
    parts = [part for part in path.lower().split("/") if part]
    if "api" in parts:
        index = parts.index("api")
        parts = parts[index + 1 :]
    parts = [part for part in parts if part not in {"pb", "pd", "private", "public"}]
    return parts[0] if parts else ""


def _materialize_route_path(route_path: str, target_path: str) -> str:
    route_parts = [part for part in route_path.split("/") if part]
    target_parts = [part for part in target_path.split("/") if part]
    next_parts: list[str] = []
    for index, part in enumerate(route_parts):
        if re.fullmatch(r"\{[^/{}]+\}", part):
            next_parts.append(target_parts[index] if index < len(target_parts) else part)
        else:
            next_parts.append(part)
    return "/" + "/".join(next_parts)


def _gateway_prefix(path: str) -> str:
    for prefix in GATEWAY_PREFIXES:
        if path.startswith(f"{prefix}/api/"):
            return prefix
    return ""
