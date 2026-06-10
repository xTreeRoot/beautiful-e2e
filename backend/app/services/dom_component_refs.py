from __future__ import annotations

import re
from pathlib import Path


NATIVE_VIEW_TAGS = {
    "a",
    "article",
    "aside",
    "block",
    "button",
    "canvas",
    "checkbox",
    "div",
    "footer",
    "form",
    "header",
    "icon",
    "image",
    "img",
    "input",
    "label",
    "li",
    "main",
    "map",
    "nav",
    "navigator",
    "p",
    "picker",
    "radio",
    "rich-text",
    "router-link",
    "router-view",
    "scroll-view",
    "section",
    "slot",
    "span",
    "swiper",
    "swiper-item",
    "table",
    "tbody",
    "td",
    "template",
    "text",
    "textarea",
    "th",
    "thead",
    "tr",
    "ul",
    "video",
    "view",
    "web-view",
}


def component_references(content: str) -> list[str]:
    """从页面/组件源码提取显式组件引用，供前端把页面链路串到组件目标。

    这里只记录源码证据中出现的组件名或导入路径，不根据业务词做固定映射。
    """

    refs: list[str] = []
    refs.extend(_component_import_refs(content))
    refs.extend(_component_option_refs(content))
    refs.extend(_component_tag_refs(content))
    return _unique_strings(refs)[:32]


def _component_import_refs(content: str) -> list[str]:
    refs: list[str] = []
    pattern = re.compile(
        r"\bimport\s+(?P<names>[\w{}\s,.*]+?)\s+from\s+['\"](?P<path>[^'\"]+)['\"]"
    )
    for match in pattern.finditer(content):
        source_path = match.group("path")
        source_name = _component_name_from_path(source_path)
        if source_name:
            refs.append(source_name)
        for name in re.findall(r"\b[A-Z][A-Za-z0-9_]*\b", match.group("names")):
            refs.append(name)
    return refs


def _component_option_refs(content: str) -> list[str]:
    refs: list[str] = []
    for match in re.finditer(r"\bcomponents\s*:\s*{(?P<body>[^}]+)}", content, flags=re.S):
        body = match.group("body")
        refs.extend(re.findall(r"['\"]([A-Za-z][\w.-]+)['\"]\s*:", body))
        refs.extend(re.findall(r"\b([A-Z][A-Za-z0-9_]*)\b", body))
    return refs


def _component_tag_refs(content: str) -> list[str]:
    refs: list[str] = []
    for match in re.finditer(r"<([A-Za-z][\w.-]*)\b", content):
        tag = match.group(1)
        if _looks_like_component_tag(tag):
            refs.append(tag)
    return refs


def _looks_like_component_tag(tag: str) -> bool:
    lowered = tag.lower()
    if lowered in NATIVE_VIEW_TAGS:
        return False
    return "-" in tag or tag[:1].isupper()


def _component_name_from_path(value: str) -> str | None:
    stem = Path(value.split("?", 1)[0]).stem
    if stem and stem != "index":
        return stem
    parent = Path(value).parent.name
    return parent or None


def _unique_strings(values: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique
