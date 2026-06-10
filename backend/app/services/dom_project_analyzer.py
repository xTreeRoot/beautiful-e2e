from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

from app.services.dom_api_refs import api_references
from app.services.dom_component_refs import component_references


DOM_COMPILATION_USAGE_KEY = "dom_compilation"

VIEW_EXTENSIONS = {
    ".html",
    ".vue",
    ".nvue",
    ".svelte",
    ".jsx",
    ".tsx",
    ".js",
    ".ts",
    ".wxml",
    ".axml",
}
VIEW_SOURCE_EXTENSIONS = (
    ".vue",
    ".nvue",
    ".tsx",
    ".jsx",
    ".wxml",
    ".axml",
    ".svelte",
    ".html",
    ".js",
    ".ts",
)
PAGE_CONFIG_NAMES = {"app.json", "pages.json"}
SCRIPT_EXTENSIONS = {".js", ".ts"}
ROUTE_FILE_HINTS = {
    "app",
    "page",
    "pages",
    "route",
    "router",
    "routes",
}
ROUTE_API_HINTS = (
    "<Route",
    "BrowserRouter",
    "HashRouter",
    "createBrowserRouter",
    "createRouter",
    "createWebHashHistory",
    "createWebHistory",
    "definePageConfig",
    "useRoutes",
    "vue-router",
)


# 本文件保留 DOM 模块扫描门面，避免打断 RepoReader 旧入口；新增解析策略继续拆到同级服务。
class DomProjectAnalyzer:
    """识别前端项目中的用户可见页面和组件，并生成系统内可渲染草图。

    分析阶段不能假设被测项目已经能在某个本地端口运行；小程序、HTML、Vue、
    React 或 uni-app 都只先根据源码证据生成轻量 DOM 预览。后续 AI 修复编译可
    复用 `dom_compilation` 用途的供应商配置替换这里的静态草图。
    """

    def extract_modules(self, file_path: Path, rel: str, root: Path) -> list[dict[str, Any]]:
        suffix = file_path.suffix.lower()
        if file_path.name in PAGE_CONFIG_NAMES:
            return self._extract_config_pages(file_path, rel, root)
        if suffix not in VIEW_EXTENSIONS:
            return []

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []

        modules = [
            self._page_module(rel, route, source_line=line, framework=framework, content=content)
            for route, line, framework in self._route_candidates(content, rel)
        ]
        conventional = self._convention_page_route(rel, root, content)
        if conventional and not any(item.get("route") == conventional for item in modules):
            modules.append(
                self._page_module(
                    rel,
                    conventional,
                    source_line=1,
                    framework=self._framework_for_file(rel, content),
                    content=content,
                )
            )

        if not modules and self._looks_like_component_source(content, rel):
            modules.append(self._component_module(rel, content))
        return modules

    def _extract_config_pages(self, file_path: Path, rel: str, root: Path) -> list[dict[str, Any]]:
        """从页面配置中提取真实可编译页面。

        `pages.json/app.json` 只是入口清单；只有能反查到页面源码时才输出页面模块，
        避免把纯配置项误展示成可预览、可编译的页面。
        """

        try:
            parsed = json.loads(_strip_json_comments(file_path.read_text(encoding="utf-8", errors="ignore")))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(parsed, dict):
            return []

        modules: list[dict[str, Any]] = []
        for route, title in _page_entries_from_config(parsed):
            normalized_route = self._normalize_page_route(route)
            source_file = _route_implementation_source_file(
                root,
                config_source_file=rel,
                route=normalized_route,
            )
            if not source_file:
                continue
            content = _read_source_text(root, source_file)
            modules.append(
                _with_config_evidence(
                    self._page_module(
                        source_file,
                        normalized_route,
                        source_line=1,
                        framework=self._framework_for_file(source_file, content),
                        title=title,
                        content=content,
                    ),
                    config_source_file=rel,
                    source_line=1,
                )
            )
        return modules

    def _route_candidates(self, content: str, rel: str) -> list[tuple[str, int, str]]:
        if not _allows_inline_route_candidates(rel, content):
            return []

        candidates: list[tuple[str, int, str]] = []
        patterns = [
            re.compile(r"<Route\b[^>]*\bpath\s*=\s*['\"]([^'\"]+)['\"]", re.I),
            re.compile(r"\bpath\s*[:=]\s*['\"]([^'\"]+)['\"]"),
        ]
        framework = self._framework_for_file(rel, content)
        for line_number, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            for pattern in patterns:
                for match in pattern.finditer(stripped):
                    route = self._normalize_page_route(match.group(1))
                    if _looks_like_user_route(route):
                        candidates.append((route, line_number, framework))
        return _unique_route_candidates(candidates)

    def _page_module(
        self,
        source_file: str,
        route: str,
        *,
        source_line: int,
        framework: str,
        content: str,
        title: str | None = None,
    ) -> dict[str, Any]:
        name = title or _route_name(route) or _file_name(source_file)
        hints = _ui_hints(content)
        component_refs = component_references(content)
        api_refs = api_references(content)
        evidence = [f"页面入口：{route}", f"来源：{source_file}:{source_line}"]
        if hints:
            evidence.extend(hints[:4])
        module = {
            "id": _stable_id("page", source_file, route),
            "kind": "page",
            "name": name,
            "route": route,
            "source": f"{source_file}:{source_line}",
            "source_file": source_file,
            "framework": framework,
            "evidence": evidence,
            "preview": self._preview_payload(name=name, module_kind="page", route=route, hints=hints),
        }
        if component_refs:
            module["component_refs"] = component_refs
        if api_refs:
            module["api_refs"] = api_refs
        return module

    def _component_module(self, source_file: str, content: str) -> dict[str, Any]:
        name = _file_name(source_file)
        hints = _ui_hints(content)
        component_refs = component_references(content)
        api_refs = api_references(content)
        module = {
            "id": _stable_id("component", source_file, name),
            "kind": "component",
            "name": name,
            "route": None,
            "source": f"{source_file}:1",
            "source_file": source_file,
            "framework": self._framework_for_file(source_file, content),
            "evidence": [f"组件来源：{source_file}", *hints[:5]],
            "component_refs": component_refs,
            "preview": self._preview_payload(name=name, module_kind="component", route=None, hints=hints),
        }
        if api_refs:
            module["api_refs"] = api_refs
        return module

    def _preview_payload(
        self,
        *,
        name: str,
        module_kind: str,
        route: str | None,
        hints: list[str],
    ) -> dict[str, Any]:
        return {
            "strategy": "static_dom_sketch",
            "ai_usage_key": DOM_COMPILATION_USAGE_KEY,
            "html": _preview_html(name=name, module_kind=module_kind, route=route, hints=hints),
            "warnings": [
                "当前预览是源码证据生成的系统内草图，不依赖被测项目前端服务。",
                "复杂页面可交给 DOM 页面编译/修复 AI 用途进一步补全。",
            ],
        }

    def _looks_like_component_source(self, content: str, rel: str) -> bool:
        lowered = rel.lower()
        if any(part in lowered for part in ["/components/", "/views/", "/pages/", "/src/"]):
            return _contains_ui_markup(content)
        return _contains_ui_markup(content) and bool(_ui_hints(content))

    def _convention_page_route(self, rel: str, root: Path, content: str) -> str | None:
        lowered = rel.lower()
        config_route = _config_backed_page_route(rel, root)
        if config_route:
            return config_route
        if _nearest_page_config_parent(rel, root) is not None:
            return None
        if lowered.startswith("pages/"):
            if _has_page_config(root):
                return None
            return _route_from_page_file(rel.removeprefix("pages/")) if _has_page_source_evidence(rel, content) else None
        if "/pages/" in f"/{lowered}":
            tail = rel.split("/pages/", 1)[1]
            return _route_from_page_file(tail) if _has_page_source_evidence(rel, content) else None
        if lowered.startswith("app/") and rel.rsplit("/", 1)[-1].split(".", 1)[0] == "page":
            return _route_from_app_page_file(rel.removeprefix("app/"))
        if "/app/" in f"/{lowered}" and rel.rsplit("/", 1)[-1].split(".", 1)[0] == "page":
            tail = rel.split("/app/", 1)[1] if "/app/" in f"/{rel}" else rel.removeprefix("app/")
            return _route_from_app_page_file(tail)
        if lowered.endswith(".html"):
            return "/" + re.sub(r"\.html?$", "", rel, flags=re.I).removesuffix("/index")
        return None

    def _framework_for_config(self, rel: str) -> str:
        if rel.endswith("pages.json"):
            return "uni-app"
        return "mini-program"

    def _framework_for_file(self, rel: str, content: str) -> str:
        suffix = Path(rel).suffix.lower()
        if suffix in {".vue", ".nvue"}:
            return "vue"
        if suffix in {".wxml", ".axml"}:
            return "mini-program"
        if "react" in content.lower() or "<Route" in content:
            return "react"
        if "createRouter" in content or "vue-router" in content:
            return "vue"
        if suffix == ".html":
            return "html"
        return "frontend"

    def _normalize_page_route(self, value: str) -> str:
        route = value.strip()
        if not route:
            return "/"
        if route.startswith("/"):
            return route
        return f"/{route}"


def merge_dom_modules(modules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按页面入口归并模块，避免配置文件和真实页面文件重复展示。

    小程序/uni-app 常同时有 `pages.json` 和实际页面源码；前者提供标题和
    路由，后者提供控件证据。图谱层应该看到一个页面模块，而不是两张卡片。
    """

    buckets: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    order: list[tuple[str, str, str]] = []
    for module in modules:
        key = _module_merge_key(module)
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(module)
    return [_merge_module_bucket(buckets[key]) for key in order]


def _strip_json_comments(value: str) -> str:
    without_block = re.sub(r"/\*.*?\*/", "", value, flags=re.S)
    return re.sub(r"^\s*//.*$", "", without_block, flags=re.M)


def _page_entries_from_config(parsed: dict[str, Any]) -> list[tuple[str, str | None]]:
    entries: list[tuple[str, str | None]] = []
    entries.extend(_page_entries(parsed.get("pages"), root=""))
    for package in parsed.get("subPackages") or parsed.get("subpackages") or []:
        if not isinstance(package, dict):
            continue
        root = str(package.get("root") or "").strip("/")
        entries.extend(_page_entries(package.get("pages"), root=root))
    return entries


def _page_entries(value: Any, *, root: str) -> list[tuple[str, str | None]]:
    if not isinstance(value, list):
        return []
    entries: list[tuple[str, str | None]] = []
    for item in value:
        title: str | None = None
        if isinstance(item, str):
            route = item
        elif isinstance(item, dict):
            route = str(item.get("path") or "").strip()
            style = item.get("style") if isinstance(item.get("style"), dict) else {}
            title_value = style.get("navigationBarTitleText") or item.get("name")
            title = str(title_value).strip() if title_value else None
        else:
            continue
        if not route:
            continue
        entries.append(("/".join(part for part in [root, route] if part), title))
    return entries


def _route_from_page_file(tail: str) -> str | None:
    route = "/" + _strip_view_extension(tail)
    route = route.removesuffix("/index")
    return route or "/"


def _config_backed_page_route(rel: str, root: Path) -> str | None:
    config_parent = _nearest_page_config_parent(rel, root)
    if config_parent is None:
        return None
    try:
        route_path = Path(rel).relative_to(config_parent).as_posix()
    except ValueError:
        return None
    route = "/" + _strip_view_extension(route_path)
    if route in _declared_page_routes(root / config_parent):
        return route
    return None


def _nearest_page_config_parent(rel: str, root: Path) -> Path | None:
    rel_path = Path(rel)
    candidates = [rel_path.parent, *rel_path.parents]
    for parent in candidates:
        if any((root / parent / name).exists() for name in PAGE_CONFIG_NAMES):
            return parent
    return None


def _declared_page_routes(config_dir: Path) -> set[str]:
    routes: set[str] = set()
    for name in PAGE_CONFIG_NAMES:
        config_path = config_dir / name
        if not config_path.exists():
            continue
        try:
            parsed = json.loads(_strip_json_comments(config_path.read_text(encoding="utf-8", errors="ignore")))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(parsed, dict):
            continue
        for route, _title in _page_entries_from_config(parsed):
            routes.add("/" + route.strip("/"))
    return routes


def _route_from_app_page_file(tail: str) -> str | None:
    parts = tail.split("/")
    if parts[-1].split(".", 1)[0] != "page":
        return None
    route = "/" + "/".join(parts[:-1])
    route = route.replace("[", ":").replace("]", "")
    return route or "/"


def _strip_view_extension(value: str) -> str:
    return re.sub(r"\.(html|vue|nvue|svelte|jsx|tsx|js|ts|wxml|axml)$", "", value, flags=re.I)


def _has_page_config(root: Path) -> bool:
    return any((root / name).exists() for name in PAGE_CONFIG_NAMES)


def _looks_like_user_route(route: str) -> bool:
    if route in {"*", "/"}:
        return True
    if route.startswith(("http://", "https://")):
        return False
    return not any(token in route for token in ["${", "{{", "node_modules"])


def _allows_inline_route_candidates(rel: str, content: str) -> bool:
    suffix = Path(rel).suffix.lower()
    if suffix in {".jsx", ".tsx"}:
        return any(token in content for token in ROUTE_API_HINTS)
    if suffix in SCRIPT_EXTENSIONS:
        return _looks_like_route_definition_file(rel, content)
    return suffix in {".vue", ".svelte", ".html"} and any(token in content for token in ROUTE_API_HINTS)


def _has_page_source_evidence(rel: str, content: str) -> bool:
    suffix = Path(rel).suffix.lower()
    if suffix in {".vue", ".nvue", ".wxml", ".axml", ".svelte", ".html"}:
        return True
    if suffix in {".jsx", ".tsx", ".js", ".ts"}:
        return _contains_ui_markup(content) or any(token in content for token in ROUTE_API_HINTS)
    return False


def _looks_like_route_definition_file(rel: str, content: str) -> bool:
    path = Path(rel)
    parts = {part.lower() for part in path.with_suffix("").parts}
    stem = path.stem.lower()
    if not (parts & ROUTE_FILE_HINTS or any(hint in stem for hint in ROUTE_FILE_HINTS)):
        return False
    return any(token in content for token in ROUTE_API_HINTS) or re.search(
        r"\broutes?\s*[:=]\s*\[",
        content,
    ) is not None


def _unique_route_candidates(candidates: list[tuple[str, int, str]]) -> list[tuple[str, int, str]]:
    seen: set[str] = set()
    unique: list[tuple[str, int, str]] = []
    for route, line, framework in candidates:
        if route in seen:
            continue
        seen.add(route)
        unique.append((route, line, framework))
    return unique


def _contains_ui_markup(content: str) -> bool:
    return bool(
        re.search(r"<(template|view|div|section|main|button|input|form|text|image)\b", content, re.I)
        or any(token in content for token in ["data-testid", "aria-label", "placeholder", "bindtap"])
    )


def _ui_hints(content: str) -> list[str]:
    hints: list[str] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if any(
            token in line
            for token in ["data-testid", "aria-label", "placeholder", "<button", "<input", "<form", "bindtap"]
        ):
            hints.append(line[:160])
        if len(hints) >= 12:
            break
    return hints


def _preview_html(
    *,
    name: str,
    module_kind: str,
    route: str | None,
    hints: list[str],
) -> str:
    title = html.escape(name or "未命名页面")
    subtitle = "页面模块" if module_kind == "page" else "组件模块"
    route_label = html.escape(route or "无页面路由")
    hint_cards = "\n".join(_preview_hint_card(hint) for hint in hints[:8])
    if not hint_cards:
        hint_cards = "<p class=\"empty\">暂无可提取控件，等待 AI 修复编译补全页面结构。</p>"
    return f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <style>
    body {{ margin: 0; background: #f7f6f2; color: #222833; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    main {{ min-height: 100vh; padding: 18px; }}
    header {{ border: 1px solid #d8eee7; border-radius: 8px; background: #eef8f5; padding: 14px; }}
    h1 {{ margin: 0 0 6px; font-size: 20px; line-height: 1.25; }}
    .meta {{ color: #746f65; font-size: 12px; }}
    .grid {{ display: grid; gap: 10px; margin-top: 14px; }}
    .card {{ border: 1px solid #eee8dc; border-radius: 8px; background: #fffefa; padding: 12px; }}
    .label {{ color: #6b6257; font-size: 12px; font-weight: 800; }}
    .hint {{ margin-top: 6px; color: #333a45; font-family: SFMono-Regular, Consolas, monospace; font-size: 12px; white-space: pre-wrap; word-break: break-word; }}
    .empty {{ margin: 0; color: #746f65; }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>{title}</h1>
      <div class=\"meta\">{subtitle} · {route_label} · 系统内静态 DOM 草图</div>
    </header>
    <section class=\"grid\">{hint_cards}</section>
  </main>
</body>
</html>"""


def _preview_hint_card(hint: str) -> str:
    return (
        "<article class=\"card\">"
        "<div class=\"label\">DOM 证据</div>"
        f"<div class=\"hint\">{html.escape(hint)}</div>"
        "</article>"
    )


def _module_merge_key(module: dict[str, Any]) -> tuple[str, str, str]:
    kind = _text(module.get("kind")) or "component"
    route = _text(module.get("route"))
    source_file = _text(module.get("source_file")) or _parse_source_file(_text(module.get("source")))
    if kind == "page" and route:
        return ("page", _canonical_page_route(route), "")
    return (kind, source_file, _text(module.get("name")))


def _merge_module_bucket(bucket: list[dict[str, Any]]) -> dict[str, Any]:
    base = dict(max(bucket, key=_module_score))
    route = _best_route(bucket) or _text(base.get("route")) or None
    source_module = max(bucket, key=_source_score)
    preview_module = max(bucket, key=_preview_score)
    name_module = max(bucket, key=_name_score)
    evidence = _merged_evidence(bucket)

    if route:
        base["route"] = route
    base["name"] = _text(name_module.get("name")) or _text(base.get("name")) or _route_name(route or "")
    base["source"] = _text(source_module.get("source")) or _text(base.get("source"))
    base["source_file"] = _text(source_module.get("source_file")) or _text(base.get("source_file"))
    base["framework"] = _text(source_module.get("framework")) or _text(base.get("framework"))
    base["evidence"] = evidence
    component_refs = _merged_text_list(bucket, "component_refs")
    if component_refs:
        base["component_refs"] = component_refs
    api_refs = _merged_text_list(bucket, "api_refs")
    if api_refs:
        base["api_refs"] = api_refs
    config_source_file = _first_text_value(bucket, "config_source_file")
    config_source = _first_text_value(bucket, "config_source")
    if config_source_file:
        base["config_source_file"] = config_source_file
    if config_source:
        base["config_source"] = config_source
    preview = dict(preview_module.get("preview") or base.get("preview") or {})
    if preview.get("html"):
        preview["html"] = _preview_html(
            name=_text(base.get("name")),
            module_kind=_text(base.get("kind")) or "component",
            route=route,
            hints=_preview_hints_from_evidence(evidence),
        )
    base["preview"] = preview
    if _text(base.get("kind")) == "page" and route:
        base["id"] = _stable_id("page", _canonical_page_route(route))
    return base


def _module_score(module: dict[str, Any]) -> tuple[int, int, int]:
    return (_source_score(module), _preview_score(module), _name_score(module))


def _source_score(module: dict[str, Any]) -> int:
    source_file = _text(module.get("source_file")) or _parse_source_file(_text(module.get("source")))
    return 0 if Path(source_file).name in PAGE_CONFIG_NAMES else 1


def _preview_score(module: dict[str, Any]) -> int:
    preview = module.get("preview") if isinstance(module.get("preview"), dict) else {}
    html_value = _text(preview.get("html")) if isinstance(preview, dict) else ""
    return len(html_value)


def _name_score(module: dict[str, Any]) -> int:
    name = _text(module.get("name"))
    route = _text(module.get("route"))
    if not name:
        return 0
    if name in {"index", "page"} or "/" in name:
        return 1
    if route and name == _route_name(route):
        return 2
    return 3


def _best_route(bucket: list[dict[str, Any]]) -> str | None:
    routes = [_text(module.get("route")) for module in bucket if _text(module.get("route"))]
    if not routes:
        return None
    return max(routes, key=lambda route: (route.endswith("/index"), len(route), route))


def _merged_evidence(bucket: list[dict[str, Any]]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for module in bucket:
        raw_evidence = module.get("evidence")
        if not isinstance(raw_evidence, list):
            continue
        for item in raw_evidence:
            value = _text(item)
            if not value or value in seen:
                continue
            seen.add(value)
            merged.append(value)
            if len(merged) >= 12:
                return merged
    return merged


def _preview_hints_from_evidence(evidence: list[str]) -> list[str]:
    return [
        item
        for item in evidence
        if not item.startswith(("页面入口：", "页面配置：", "组件来源：", "来源："))
    ]


def _first_text_value(bucket: list[dict[str, Any]], field: str) -> str:
    for module in bucket:
        value = _text(module.get(field))
        if value:
            return value
    return ""


def _merged_text_list(bucket: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for module in bucket:
        raw_values = module.get(field)
        if not isinstance(raw_values, list):
            continue
        values.extend(_text(item) for item in raw_values)
    return _unique_strings([value for value in values if value])


def _canonical_page_route(route: str) -> str:
    normalized = route if route.startswith("/") else f"/{route}"
    normalized = re.sub(r"/+", "/", normalized)
    if normalized != "/" and normalized.endswith("/index"):
        return normalized.removesuffix("/index") or "/"
    return normalized


def _parse_source_file(source: str) -> str:
    separator_index = source.rfind(":")
    if separator_index < 0:
        return source
    raw_line = source[separator_index + 1 :]
    return source[:separator_index] if raw_line.isdigit() else source


def _with_config_evidence(
    module: dict[str, Any],
    *,
    config_source_file: str,
    source_line: int,
) -> dict[str, Any]:
    module["config_source_file"] = config_source_file
    module["config_source"] = f"{config_source_file}:{source_line}"
    evidence = module.get("evidence") if isinstance(module.get("evidence"), list) else []
    module["evidence"] = [
        *(evidence[:1] if evidence else []),
        f"页面配置：{config_source_file}:{source_line}",
        *evidence[1:],
    ]
    return module


def _route_implementation_source_file(
    root: Path,
    *,
    config_source_file: str,
    route: str,
) -> str | None:
    if Path(config_source_file).name not in PAGE_CONFIG_NAMES or not route.strip():
        return None

    root_path = root.expanduser().resolve()
    config_path = (root_path / config_source_file).resolve()
    try:
        config_path.relative_to(root_path)
    except ValueError:
        return None

    route_stems = _route_source_stems(route)
    for base in _candidate_source_bases(root_path, config_path.parent):
        for stem in route_stems:
            for extension in VIEW_SOURCE_EXTENSIONS:
                candidate = (base / f"{stem}{extension}").resolve()
                relative = _relative_source_file(root_path, candidate)
                if relative and candidate.is_file():
                    return relative
    return None


def _candidate_source_bases(root_path: Path, config_dir: Path) -> list[Path]:
    candidates = [config_dir, config_dir / "src", root_path, root_path / "src"]
    bases: list[Path] = []
    for base in candidates:
        resolved = base.resolve()
        if resolved not in bases:
            bases.append(resolved)
    return bases


def _route_source_stems(route: str) -> list[str]:
    normalized = route.split("?", 1)[0].split("#", 1)[0].strip().strip("/")
    if not normalized:
        return []

    stems = [normalized]
    if not normalized.endswith("/index"):
        stems.append(f"{normalized}/index")
    if not normalized.startswith("pages/"):
        stems.append(f"pages/{normalized}")
        if not normalized.endswith("/index"):
            stems.append(f"pages/{normalized}/index")
    return _unique_strings(stems)


def _relative_source_file(root_path: Path, candidate: Path) -> str | None:
    try:
        return candidate.relative_to(root_path).as_posix()
    except ValueError:
        return None


def _read_source_text(root: Path, source_file: str) -> str:
    try:
        return (root / source_file).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _unique_strings(values: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _route_name(route: str) -> str:
    stripped = route.strip("/")
    if not stripped:
        return "首页"
    return stripped.rsplit("/", 1)[-1] or stripped


def _file_name(path: str) -> str:
    return Path(path).stem or Path(path).name or "未命名模块"


def _stable_id(*parts: str) -> str:
    raw = ":".join(parts)
    return re.sub(r"[^a-zA-Z0-9_.:-]+", "-", raw).strip("-")[:180]
