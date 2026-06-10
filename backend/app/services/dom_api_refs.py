from __future__ import annotations

import re
from urllib.parse import urlparse


API_REFERENCE_PATTERNS = (
    re.compile(r"\bfetch\s*\(\s*['\"](?P<value>[^'\"]+)['\"]"),
    re.compile(r"\baxios\s*\(\s*['\"](?P<value>[^'\"]+)['\"]"),
    re.compile(r"\baxios\.(?:get|post|put|delete|patch)\s*\(\s*['\"](?P<value>[^'\"]+)['\"]"),
    re.compile(r"\b(?:url|requestUrl|apiUrl)\s*[:=]\s*['\"](?P<value>[^'\"]+)['\"]"),
)


def api_references(content: str) -> list[str]:
    """从前端源码提取明确接口引用，供 DOM 图谱联动后端真实路由。

    只收录看起来像接口路径的字符串，避免把普通页面路由或静态资源误连到接口。
    """

    refs: list[str] = []
    for pattern in API_REFERENCE_PATTERNS:
        for match in pattern.finditer(content):
            normalized = _normalize_api_reference(match.group("value"))
            if normalized:
                refs.append(normalized)
    return _unique_strings(refs)[:32]


def _normalize_api_reference(value: str) -> str | None:
    raw = value.strip()
    if not raw or any(token in raw for token in ["${", "{{", "node_modules"]):
        return None

    parsed = urlparse(raw)
    path = parsed.path if parsed.scheme and parsed.netloc else raw.split("?", 1)[0].split("#", 1)[0]
    if not path.startswith("/"):
        path = f"/{path}"
    path = re.sub(r"/+", "/", path)
    if _looks_like_api_path(path):
        return path
    return None


def _looks_like_api_path(path: str) -> bool:
    lowered = path.lower()
    return lowered.startswith("/api/") or "/api/" in lowered or lowered.endswith("/api")


def _unique_strings(values: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique
