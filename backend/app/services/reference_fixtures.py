from __future__ import annotations

import re
from typing import Any

ID_FIELD_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*Id$")
LONG_ID_PATTERN = re.compile(r"\d{6,}")

NAME_FIELD_PRIORITIES = {
    "goodsName": 120,
    "goods_name": 120,
    "商品名称": 120,
    "商品名": 120,
    "campaignName": 105,
    "campaign_name": 105,
    "活动名称": 105,
    "activityName": 100,
    "activity_name": 100,
    "displayTitle": 95,
    "display_title": 95,
    "页面主标题": 95,
    "主标题": 90,
    "标题": 80,
    "title": 80,
    "name": 60,
}

GENERIC_TABLE_HEADERS = {
    "字段",
    "名称",
    "名",
    "key",
    "name",
    "field",
    "值",
    "value",
    "类型",
    "type",
}

NAME_FIELD_TOKENS = ("name", "title", "名称", "标题")
SEARCH_FIELD_TOKENS = ("goodsname", "campaignname", "activityname", "displaytitle", "name", "title")


def extract_reference_fixtures(reference_documents: list[dict[str, Any]]) -> dict[str, Any]:
    """从引用文档中抽取固定测试夹具和可复用业务名称。

    远程模型不能直接遍历本地文档目录，且容易把地名、范围词或短关键词当作实体名。
    这里把执行单中的固定 ID、活动标题和示例名称整理成结构化事实，供生成、
    项目分析上下文和后处理统一复用。
    """

    fixed_ids: dict[str, dict[str, Any]] = {}
    entity_names: list[dict[str, Any]] = []
    seen_names: set[tuple[str, str]] = set()

    for document in reference_documents:
        source = str(document.get("title") or document.get("path") or "参考文档")
        content = str(document.get("content") or "")
        for line in content.splitlines():
            cells = _markdown_table_cells(line)
            if len(cells) >= 2 and not _is_table_header_row(cells):
                _capture_pair(cells[0], cells[1], " | ".join(cells[2:]), source, fixed_ids, entity_names, seen_names)
                continue

            for key, value in _json_string_pairs(line):
                _capture_pair(key, value, "", source, fixed_ids, entity_names, seen_names)

    return {
        "fixed_ids": fixed_ids,
        "entity_names": sorted(
            entity_names,
            key=lambda item: (int(item.get("priority") or 0), len(str(item.get("value") or ""))),
            reverse=True,
        )[:24],
    }


def fixed_id_values(fixtures: dict[str, Any]) -> dict[str, str]:
    """返回 `{字段名: ID}` 形式，兼容已有路径模板替换逻辑。"""

    raw_ids = fixtures.get("fixed_ids")
    if not isinstance(raw_ids, dict):
        return {}
    values: dict[str, str] = {}
    for key, item in raw_ids.items():
        if isinstance(item, dict) and item.get("value"):
            values[str(key)] = str(item["value"])
    return values


def compact_reference_fixtures(fixtures: dict[str, Any]) -> dict[str, Any]:
    """压缩夹具信息，避免在 DSL 节点上重复写入整份文档内容。"""

    compact: dict[str, Any] = {}
    ids = fixed_id_values(fixtures)
    if ids:
        compact["fixed_ids"] = ids
    names = fixtures.get("entity_names")
    if isinstance(names, list) and names:
        compact["entity_names"] = [
            {
                "field": item.get("field"),
                "value": item.get("value"),
                "source": item.get("source"),
            }
            for item in names[:8]
            if isinstance(item, dict)
        ]
    return compact


def best_reference_search_term(
    fixtures: dict[str, Any],
    *,
    field: str,
    current_value: Any = None,
    route: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """为搜索/分页字段选择比短关键词更可靠的文档实体名。"""

    names = fixtures.get("entity_names")
    if not isinstance(names, list):
        return None

    current_text = str(current_value or "").strip()
    ranked: list[tuple[int, dict[str, Any]]] = []
    for item in names:
        if not isinstance(item, dict):
            continue
        value = str(item.get("value") or "").strip()
        if not _looks_like_business_name(value):
            continue
        score = int(item.get("priority") or 0)
        score += _field_affinity_score(field, str(item.get("field") or ""))
        if current_text:
            if current_text == value:
                continue
            if current_text in value:
                score += 60
            elif len(current_text) >= 4:
                continue
        if route:
            route_text = _route_text(route)
            if "goods" in route_text or "商品" in route_text:
                score += _field_affinity_score("goodsName", str(item.get("field") or "")) // 2
            if "campaign" in route_text or "活动" in route_text:
                score += _field_affinity_score("campaignName", str(item.get("field") or "")) // 2
        ranked.append((score + min(len(value), 40), item))

    if not ranked:
        return None
    ranked.sort(key=lambda entry: entry[0], reverse=True)
    return ranked[0][1]


def fixture_parameter_links_for_target(
    *,
    target_url: str | None,
    route_template: str | None,
    fixtures: dict[str, Any],
) -> list[dict[str, Any]]:
    """把路径里的固定 ID 标注为显式测试夹具，避免被诊断为凭空硬编码。"""

    id_values = fixed_id_values(fixtures)
    if not target_url or not route_template or not id_values:
        return []

    target_parts = [part for part in target_url.split("?", 1)[0].split("/") if part]
    if target_parts and target_parts[0] in {"customer", "merchant", "admin"}:
        target_parts = target_parts[1:]
    template_parts = [part for part in route_template.split("/") if part]

    links: list[dict[str, Any]] = []
    for index, template_part in enumerate(template_parts):
        match = re.fullmatch(r"\{([^/{}]+)\}", template_part)
        if not match or index >= len(target_parts):
            continue
        variable = match.group(1)
        literal = target_parts[index]
        if id_values.get(variable) != literal:
            continue
        fixture = fixtures.get("fixed_ids", {}).get(variable, {})
        links.append(
            {
                "variable": variable,
                "value": literal,
                "location": "target_url",
                "source": fixture.get("source"),
                "reason": "引用文档声明的固定测试夹具 explicit_fixture。",
            }
        )
    return links


def _capture_pair(
    raw_key: str,
    raw_value: str,
    description: str,
    source: str,
    fixed_ids: dict[str, dict[str, Any]],
    entity_names: list[dict[str, Any]],
    seen_names: set[tuple[str, str]],
) -> None:
    key = _clean_cell(raw_key)
    value = _clean_cell(raw_value)
    detail = _clean_cell(description)
    if not key:
        return

    if ID_FIELD_PATTERN.fullmatch(key):
        id_value = _first_long_id(value) or _first_long_id(detail)
        if id_value:
            fixed_ids.setdefault(
                key,
                {
                    "name": key,
                    "value": id_value,
                    "description": detail,
                    "source": source,
                },
            )

    name_value = _name_value_from_pair(key, value, detail)
    if not name_value:
        return
    normalized_key = _normalized_name_field(key)
    seen_key = (normalized_key, name_value)
    if seen_key in seen_names:
        return
    seen_names.add(seen_key)
    entity_names.append(
        {
            "field": key,
            "normalized_field": normalized_key,
            "value": name_value,
            "description": detail,
            "source": source,
            "priority": _name_field_priority(key),
        }
    )


def _name_value_from_pair(key: str, value: str, description: str) -> str | None:
    if not _is_name_field(key):
        return None
    candidates = [value, *_quoted_values(description)]
    for candidate in candidates:
        text = candidate.strip()
        if _looks_like_business_name(text):
            return text
    return None


def _markdown_table_cells(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or "|" not in stripped[1:]:
        return []
    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    if len(cells) < 2:
        return []
    if all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells):
        return []
    return cells


def _is_table_header_row(cells: list[str]) -> bool:
    normalized = {_clean_cell(cell).lower() for cell in cells[:3]}
    return len(normalized & {item.lower() for item in GENERIC_TABLE_HEADERS}) >= 2


def _json_string_pairs(line: str) -> list[tuple[str, str]]:
    return [
        (match.group(1), match.group(2))
        for match in re.finditer(r'"([A-Za-z_][A-Za-z0-9_]*)"\s*:\s*"([^"]+)"', line)
    ]


def _clean_cell(value: str) -> str:
    text = value.strip()
    text = re.sub(r"^\*\*(.+)\*\*$", r"\1", text)
    return text.strip("`'\"“”‘’ ")


def _first_long_id(value: str) -> str | None:
    match = LONG_ID_PATTERN.search(value)
    return match.group(0) if match else None


def _quoted_values(value: str) -> list[str]:
    return [match.group(1).strip() for match in re.finditer(r"`([^`]+)`", value)]


def _is_name_field(field: str) -> bool:
    normalized = _normalized_name_field(field)
    if normalized in {_normalized_name_field(item) for item in NAME_FIELD_PRIORITIES}:
        return True
    return any(token in normalized.lower() for token in NAME_FIELD_TOKENS)


def _normalized_name_field(field: str) -> str:
    text = re.sub(r"[_\-\s]+", "", field.strip())
    return text.lower()


def _name_field_priority(field: str) -> int:
    normalized = _normalized_name_field(field)
    for known_field, priority in NAME_FIELD_PRIORITIES.items():
        if _normalized_name_field(known_field) == normalized:
            return priority
    if any(token in normalized for token in ("商品", "goods")):
        return 100
    if any(token in normalized for token in ("活动", "campaign", "activity")):
        return 90
    if any(token in normalized for token in ("标题", "title")):
        return 80
    return 50


def _field_affinity_score(target_field: str, fixture_field: str) -> int:
    normalized_target = _normalized_name_field(target_field)
    normalized_fixture = _normalized_name_field(fixture_field)
    if normalized_target == normalized_fixture:
        return 80
    if normalized_target == "goodsname":
        if any(token in normalized_fixture for token in ("goods", "商品")):
            return 70
        if any(token in normalized_fixture for token in ("campaign", "activity", "活动", "displaytitle", "标题")):
            return 35
    if normalized_target in {"campaignname", "activityname"}:
        if any(token in normalized_fixture for token in ("campaign", "activity", "活动")):
            return 70
        if any(token in normalized_fixture for token in ("displaytitle", "标题")):
            return 45
    if any(token in normalized_fixture for token in SEARCH_FIELD_TOKENS):
        return 20
    return 0


def _looks_like_business_name(value: str) -> bool:
    if len(value) < 4 or len(value) > 80:
        return False
    if value in {"string", "String", "值", "无", "是", "否", "true", "false"}:
        return False
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        return False
    if re.match(r"https?://|/", value):
        return False
    return bool(re.search(r"[\u4e00-\u9fffA-Za-z]", value))


def _route_text(route: dict[str, Any]) -> str:
    values = [
        route.get("method"),
        route.get("path"),
        route.get("summary"),
        route.get("description"),
        route.get("handler"),
        route.get("source"),
    ]
    return " ".join(str(value or "") for value in values).lower()
