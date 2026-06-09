from __future__ import annotations

import re
from typing import Any

ENTRYPOINT_INTENT_EXPANSIONS = {
    "分页": ("page", "list"),
    "列表": ("list", "page"),
    "搜索": ("search", "query", "list", "page"),
    "查询": ("query", "search", "get", "list", "page"),
    "详情": ("detail", "info", "get"),
    "首页": ("home", "index"),
}

DISCOVERY_ENTRYPOINT_TOKENS = {
    "分页",
    "列表",
    "搜索",
    "查询",
    "page",
    "list",
    "search",
    "query",
}

FIXTURE_OVERRIDE_TOKENS = (
    "固定id",
    "固定 id",
    "固定ID",
    "指定id",
    "指定 id",
    "指定ID",
    "直接使用id",
    "直接使用 ID",
    "使用固定",
    "用固定",
)

DYNAMIC_DISCOVERY_TOKENS = (
    "真实找到",
    "找到",
    "查出来",
    "查询出来",
    "搜索出来",
    "从客户端",
    "从用户端",
    "不要直接",
    "再用",
    "传给",
    "进入详情",
)


def flow_entrypoint_from_prompt(prompt: str) -> dict[str, Any]:
    """从自然语言中提取显式流程起点，作为生成和后处理的共享契约。

    这里只抽取“从/入口/起点/先从”这类通用表达，不理解具体业务名，避免把某个
    项目案例写死进生成器。
    """

    raw_text = extract_entrypoint_text(prompt)
    rules = [
        "第一个可执行步骤必须匹配 raw_text 对应的真实接口。",
        "入口发现接口要先于详情、目标业务动作、提交或结果查询接口。",
        "如果 raw_text 是列表/分页/搜索/查询意图，首步应生产下游业务实体 ID。",
    ]
    return {
        "explicit": bool(raw_text),
        "raw_text": raw_text,
        "must_be_first_executable_step": bool(raw_text),
        "source": "natural_language" if raw_text else None,
        "requires_dynamic_discovery": dynamic_entity_discovery_required(
            prompt,
            raw_text=raw_text,
        ),
        "terms": entrypoint_terms(raw_text or ""),
        "rules": rules,
    }


def extract_entrypoint_text(prompt: str) -> str | None:
    """抽取用户明确声明的流程入口文本。"""

    normalized = re.sub(r"\s+", " ", prompt).strip()
    patterns = [
        r"(?:不要直接[^，。；;]*[，,]\s*)?要从(?P<entry>.+?)(?:开始|起|再|然后|并|，|。|；|;|$)",
        r"(?:先|首先)?从(?P<entry>.+?)(?:开始|起|再|然后|并|，|。|；|;|$)",
        r"(?:入口|起点)(?:是|为|从)?(?P<entry>.+?)(?:开始|起|再|然后|并|，|。|；|;|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if not match:
            continue
        entry = clean_entrypoint_text(match.group("entry"))
        if entry:
            return entry
    return None


def clean_entrypoint_text(value: str) -> str | None:
    """清理入口短语中与路由匹配无关的外层动作词。"""

    cleaned = value.strip(" ：:，,。；;")
    cleaned = re.sub(r"^(?:客户端|用户端|前端)", "", cleaned).strip()
    cleaned = re.sub(r"^(?:打开|进入|调用|请求)", "", cleaned).strip()
    cleaned = re.sub(r"(?:的)?(?:流程|接口链路|测试用例|全流程)$", "", cleaned).strip()
    if len(cleaned) < 2:
        return None
    return cleaned[:80]


def dynamic_entity_discovery_required(
    prompt: str,
    *,
    raw_text: str | None = None,
) -> bool:
    """判断固定夹具 ID 是否应降级为候选数据，而不是直接消费。

    当用户要求“从查询/分页/搜索开始并真实找到实体”时，下游 ID 必须来自上游
    响应 extract。只有用户明确说固定 ID 或指定 ID 时，文档夹具才可满足依赖。
    """

    compact_prompt = re.sub(r"\s+", "", prompt)
    lowered_prompt = compact_prompt.lower()
    if any(token in compact_prompt or token.lower() in lowered_prompt for token in FIXTURE_OVERRIDE_TOKENS):
        return False

    entry = raw_text or extract_entrypoint_text(prompt) or ""
    entry_terms = set(entrypoint_terms(entry))
    has_discovery_entry = bool(entry_terms & DISCOVERY_ENTRYPOINT_TOKENS)
    has_dynamic_phrase = any(token in compact_prompt for token in DYNAMIC_DISCOVERY_TOKENS)
    return has_discovery_entry and has_dynamic_phrase


def entrypoint_terms(text: str) -> list[str]:
    """把入口短语展开成可用于路由匹配的中英文关键词。"""

    terms: list[str] = []
    normalized = text.strip()
    if not normalized:
        return []

    terms.append(normalized.lower())
    for token, values in ENTRYPOINT_INTENT_EXPANSIONS.items():
        if token in normalized:
            terms.append(token)
            terms.extend(values)

    chinese_terms = re.findall(r"[\u4e00-\u9fff]{2,}", normalized)
    for term in chinese_terms:
        terms.append(term)
        for width in range(2, min(4, len(term)) + 1):
            terms.extend(term[index : index + width] for index in range(len(term) - width + 1))

    lexical = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", normalized)
    terms.extend(
        item
        for item in re.split(r"[^A-Za-z0-9]+", lexical.lower())
        if len(item) >= 2 and item not in {"api", "http", "test", "case"}
    )
    return list(dict.fromkeys(term for term in terms if term))
