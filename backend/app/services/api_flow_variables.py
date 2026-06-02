from __future__ import annotations

from collections.abc import Mapping
import json
import re
from typing import Any

PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([A-Za-z_][\w.-]*)\s*\}\}")
EXACT_PLACEHOLDER_PATTERN = re.compile(r"^\{\{\s*([A-Za-z_][\w.-]*)\s*\}\}$")


class MissingApiFlowVariableError(ValueError):
    """接口步骤引用了尚未由前置响应提取出的变量。"""

    def __init__(self, variable_name: str) -> None:
        super().__init__(f"接口步骤引用的变量未解析：{variable_name}")
        self.variable_name = variable_name


def resolve_dynamic_value(value: Any, variables: Mapping[str, Any]) -> Any:
    """递归解析接口步骤里的 `{{变量}}` 占位符。

    整个字段都是占位符时保留原始类型，例如数字 id 仍然是数字；嵌入字符串时
    转成字符串拼接，便于 URL 和 header 场景使用。
    """
    if isinstance(value, str):
        exact_match = EXACT_PLACEHOLDER_PATTERN.fullmatch(value.strip())
        if exact_match:
            return _variable_value(exact_match.group(1), variables)

        def replace(match: re.Match[str]) -> str:
            variable = match.group(1)
            return str(_variable_value(variable, variables))

        return PLACEHOLDER_PATTERN.sub(replace, value)

    if isinstance(value, list):
        return [resolve_dynamic_value(item, variables) for item in value]

    if isinstance(value, dict):
        return {
            str(key): resolve_dynamic_value(item, variables)
            for key, item in value.items()
        }

    return value


def extract_response_variables(body: bytes, extract_spec: Any) -> dict[str, Any]:
    """按步骤声明的 `extract` 契约从 JSON 响应中提取变量。

    支持两种常见写法：`{"token": "$.data.token"}`，以及
    `[{"name": "token", "path": "$.data.token"}]`。选择器为空时会按字段名
    在响应 JSON 中递归查找，作为文档不完整时的兜底。
    """
    if not extract_spec:
        return {}

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}

    extracted: dict[str, Any] = {}
    for name, selectors in _extract_entries(extract_spec):
        for selector in selectors:
            value = _read_selector(payload, selector or name)
            if value is not None:
                extracted[name] = value
                break
    return extracted


def placeholders_in_value(value: Any) -> set[str]:
    """收集接口 URL、headers 或 body 中声明的变量占位符。"""
    if isinstance(value, str):
        return {match.group(1) for match in PLACEHOLDER_PATTERN.finditer(value)}
    if isinstance(value, list):
        return {item for entry in value for item in placeholders_in_value(entry)}
    if isinstance(value, dict):
        placeholders: set[str] = set()
        for item in value.values():
            placeholders.update(placeholders_in_value(item))
        return placeholders
    return set()


def _variable_value(variable_name: str, variables: Mapping[str, Any]) -> Any:
    if variable_name not in variables:
        raise MissingApiFlowVariableError(variable_name)
    return variables[variable_name]


def _extract_entries(extract_spec: Any) -> list[tuple[str, list[str]]]:
    if isinstance(extract_spec, dict):
        entries: list[tuple[str, list[str]]] = []
        for raw_name, raw_selector in extract_spec.items():
            name = str(raw_name).strip()
            if not name:
                continue
            entries.append((name, _selector_list(raw_selector)))
        return entries

    if isinstance(extract_spec, list):
        entries = []
        for item in extract_spec:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("variable") or "").strip()
            if not name:
                continue
            selectors = _selector_list(
                item.get("path")
                or item.get("json_path")
                or item.get("selector")
                or item.get("selectors")
            )
            entries.append((name, selectors))
        return entries

    return []


def _selector_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    selector = str(value).strip()
    return [selector] if selector else []


def _read_selector(payload: Any, selector: str) -> Any:
    if not selector:
        return None
    if selector.startswith("$"):
        return _read_json_path(payload, selector)
    return _find_field(payload, selector)


def _read_json_path(payload: Any, path: str) -> Any:
    cursor = payload
    for token in _json_path_tokens(path):
        if cursor is None:
            return None
        if isinstance(token, int):
            if not isinstance(cursor, list) or token >= len(cursor):
                return None
            cursor = cursor[token]
            continue
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(token)
    return cursor


def _json_path_tokens(path: str) -> list[str | int]:
    text = path.strip()
    if text == "$":
        return []
    if text.startswith("$."):
        text = text[2:]
    elif text.startswith("$"):
        text = text[1:].lstrip(".")

    tokens: list[str | int] = []
    for part in filter(None, text.split(".")):
        name_match = re.match(r"([A-Za-z_][\w-]*)", part)
        if name_match:
            tokens.append(name_match.group(1))
        for index_match in re.finditer(r"\[(\d+)\]", part):
            tokens.append(int(index_match.group(1)))
    return tokens


def _find_field(payload: Any, field_name: str) -> Any:
    if isinstance(payload, dict):
        if field_name in payload:
            return payload[field_name]
        for value in payload.values():
            found = _find_field(value, field_name)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _find_field(item, field_name)
            if found is not None:
                return found
    return None
