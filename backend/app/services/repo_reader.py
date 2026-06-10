from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import re
from pathlib import Path
from typing import Any, Iterator

from app.services.java_spring_contracts import JavaSpringContractExtractor
from app.services.openapi_routes import OpenApiRouteExtractor


IGNORED_DIRS = {
    ".git",
    ".next",
    ".nuxt",
    ".turbo",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
}

SIGNAL_EXTENSIONS = {
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".vue",
    ".svelte",
    ".py",
    ".java",
    ".go",
    ".kt",
    ".rb",
    ".php",
    ".yaml",
    ".yml",
    ".json",
}

ROUTE_FILE_NAME_TERMS = (
    "api",
    "controller",
    "endpoint",
    "handler",
    "openapi",
    "resource",
    "route",
    "router",
    "swagger",
)

ROUTE_DIRECTORY_TERMS = (
    "/api/",
    "/controller/",
    "/controllers/",
    "/endpoint/",
    "/endpoints/",
    "/handler/",
    "/handlers/",
    "/route/",
    "/routes/",
    "/router/",
    "/routers/",
)


@dataclass(frozen=True)
class RepoSummary:
    path: str | None
    exists: bool
    files: list[str]
    signals: list[str]
    routes: list[dict[str, Any]] = field(default_factory=list)
    dom_targets: list[dict[str, Any]] = field(default_factory=list)
    auth_profile: dict[str, Any] | None = None
    analysis: dict[str, Any] | None = None
    scan: dict[str, Any] | None = None

    def as_dict(self) -> dict:
        data = {
            "path": self.path,
            "exists": self.exists,
            "files": self.files,
            "signals": self.signals,
            "routes": self.routes,
            "dom_targets": self.dom_targets,
        }
        if self.auth_profile:
            data["auth_profile"] = self.auth_profile
        if self.analysis:
            data["analysis"] = self.analysis
        if self.scan:
            data["scan"] = self.scan
        return data

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "RepoSummary":
        if not isinstance(value, dict):
            return cls(path=None, exists=False, files=[], signals=[])
        return cls(
            path=str(value.get("path")) if value.get("path") is not None else None,
            exists=bool(value.get("exists")),
            files=[str(item) for item in value.get("files", []) if isinstance(item, str)],
            signals=[str(item) for item in value.get("signals", []) if isinstance(item, str)],
            routes=[item for item in value.get("routes", []) if isinstance(item, dict)],
            dom_targets=[item for item in value.get("dom_targets", []) if isinstance(item, dict)],
            auth_profile=value.get("auth_profile") if isinstance(value.get("auth_profile"), dict) else None,
            analysis=value.get("analysis") if isinstance(value.get("analysis"), dict) else None,
            scan=value.get("scan") if isinstance(value.get("scan"), dict) else None,
        )


class RepoReader:
    def __init__(
        self,
        max_files: int = 160,
        max_routes: int = 2000,
        max_dom_targets: int = 600,
        max_scan_files: int = 12000,
    ) -> None:
        self.max_files = max_files
        self.max_routes = max_routes
        self.max_dom_targets = max_dom_targets
        self.max_scan_files = max_scan_files
        self.openapi_extractor = OpenApiRouteExtractor()
        self.spring_contract_extractor = JavaSpringContractExtractor()

    def summarize(self, raw_path: str | None) -> RepoSummary:
        if not raw_path:
            return RepoSummary(
                path=None,
                exists=False,
                files=[],
                signals=[],
                routes=[],
                scan=self._empty_scan(),
            )

        path = Path(raw_path).expanduser()
        if not path.exists() or not path.is_dir():
            return RepoSummary(
                path=str(path),
                exists=False,
                files=[],
                signals=[],
                routes=[],
                scan=self._empty_scan(),
            )

        files: list[str] = []
        signals: list[str] = []
        routes_by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
        dom_targets_by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
        scanned_count = 0

        for scanned_count, file_path in enumerate(self._iter_files(path), start=1):
            rel = file_path.relative_to(path).as_posix()
            group_key = self._scan_group_key(path, file_path)
            if len(files) < self.max_files:
                files.append(rel)
                signal = self._extract_signal(file_path, rel)
                if signal:
                    signals.append(signal)

            extracted_routes = self._extract_routes(file_path, rel, path)
            if extracted_routes:
                routes_by_group[group_key].extend(extracted_routes)

            if self._should_collect_dom_targets(group_key, dom_targets_by_group):
                dom_targets_by_group[group_key].extend(self._extract_dom_targets(file_path, rel))

        merged_routes_by_group = {
            group_key: self._merge_duplicate_routes(routes)
            for group_key, routes in routes_by_group.items()
        }
        discovered_route_count = sum(len(routes) for routes in merged_routes_by_group.values())
        routes = self._select_fair_items(merged_routes_by_group, self.max_routes)
        discovered_dom_target_count = sum(len(targets) for targets in dom_targets_by_group.values())
        dom_targets = self._select_fair_items(dom_targets_by_group, self.max_dom_targets)
        scan = self._scan_stats(
            scanned_file_count=scanned_count,
            file_count=len(files),
            route_count=len(routes),
            discovered_route_count=discovered_route_count,
            dom_target_count=len(dom_targets),
            discovered_dom_target_count=discovered_dom_target_count,
            group_count=len({*merged_routes_by_group.keys(), *dom_targets_by_group.keys()}),
        )

        return RepoSummary(
            path=str(path),
            exists=True,
            files=files,
            signals=signals[:40],
            routes=self._merge_duplicate_routes(routes)[: self.max_routes],
            dom_targets=dom_targets[: self.max_dom_targets],
            scan=scan,
        )

    def _iter_files(self, root: Path) -> Iterator[Path]:
        grouped_files: dict[str, list[Path]] = defaultdict(list)
        for file_path in root.rglob("*"):
            if not file_path.is_file():
                continue
            if any(part in IGNORED_DIRS for part in file_path.parts):
                continue
            if file_path.suffix.lower() not in SIGNAL_EXTENSIONS:
                continue
            grouped_files[self._scan_group_key(root, file_path)].append(file_path)

        for files in grouped_files.values():
            files.sort(key=lambda file_path: self._scan_priority(root, file_path))

        group_keys = sorted(grouped_files)
        max_group_size = max((len(files) for files in grouped_files.values()), default=0)
        for index in range(max_group_size):
            for group_key in group_keys:
                files = grouped_files[group_key]
                if index < len(files):
                    yield files[index]

    def _scan_group_key(self, root: Path, file_path: Path) -> str:
        module_root = self._module_root_for_file(root, file_path)
        if module_root is not None:
            return module_root.relative_to(root).as_posix()

        rel_parts = file_path.relative_to(root).parts
        if len(rel_parts) <= 1:
            return ""
        return rel_parts[0]

    def _module_root_for_file(self, root: Path, file_path: Path) -> Path | None:
        """找到文件所属的最近构建模块，用于多模块仓库公平扫描。"""

        for parent in [file_path.parent, *file_path.parents]:
            if parent == root or root not in parent.parents:
                break
            if self._looks_like_module_root(parent):
                return parent
        return None

    def _looks_like_module_root(self, path: Path) -> bool:
        return any(
            (path / marker).exists()
            for marker in ["pom.xml", "build.gradle", "build.gradle.kts", "package.json", "pyproject.toml"]
        )

    def _scan_priority(self, root: Path, file_path: Path) -> tuple[int, str]:
        """让多模块仓库先覆盖每个子模块的接口入口。

        旧逻辑按完整路径排序扫描，目录靠前的子模块会先消耗扫描额度。这里在每个顶层
        分组内优先扫描 Controller、路由和 OpenAPI 文件，再对分组做轮询，让大型
        monorepo 的后置模块也能进入初始图谱。
        """

        rel = file_path.relative_to(root).as_posix().lower()
        name = file_path.name.lower()
        if any(term in name for term in ROUTE_FILE_NAME_TERMS):
            return (0, rel)
        if any(term in f"/{rel}" for term in ROUTE_DIRECTORY_TERMS):
            return (1, rel)
        if file_path.suffix.lower() in {".yaml", ".yml", ".json"}:
            return (2, rel)
        return (10, rel)

    def _select_fair_items(
        self,
        grouped_items: dict[str, list[dict[str, Any]]],
        limit: int,
    ) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        group_keys = sorted(grouped_items)
        max_group_size = max((len(items) for items in grouped_items.values()), default=0)
        for index in range(max_group_size):
            for group_key in group_keys:
                items = grouped_items[group_key]
                if index >= len(items):
                    continue
                selected.append(items[index])
                if len(selected) >= limit:
                    return selected
        return selected

    def _should_collect_dom_targets(
        self,
        group_key: str,
        dom_targets_by_group: dict[str, list[dict[str, Any]]],
    ) -> bool:
        current_total = sum(len(targets) for targets in dom_targets_by_group.values())
        if current_total < self.max_dom_targets:
            return True
        return len(dom_targets_by_group.get(group_key, [])) == 0

    def _extract_signal(self, file_path: Path, rel: str) -> str | None:
        lowered = rel.lower()
        interesting_name = any(
            token in lowered
            for token in [
                "route",
                "router",
                "controller",
                "handler",
                "page",
                "view",
                "api",
                "service",
                "schema",
                "store",
                "auth",
                "login",
                "openapi",
                "swagger",
            ]
        )
        if not interesting_name:
            return None

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return f"{rel}: 无法读取"

        lines = [line.strip() for line in content.splitlines()[:80]]
        hints = [
            line
            for line in lines
            if any(
                token in line.lower()
                for token in ["router", "route", "app.", "get(", "post(", "path=", "testid", "data-testid"]
            )
        ][:4]
        if hints:
            return f"{rel}: " + " | ".join(hints)
        return rel

    def _extract_routes(self, file_path: Path, rel: str, root: Path) -> list[dict[str, Any]]:
        """从常见后端框架中提取轻量接口路由证据。

        生成器会把这些记录作为后端接口模式的真实依据，确保路径来自代码，
        而不是根据自然语言业务描述猜测。
        """
        suffix = file_path.suffix.lower()
        if suffix in {".json", ".yaml", ".yml"}:
            return self.openapi_extractor.extract(file_path, rel)
        if suffix not in {".java", ".kt", ".py", ".ts", ".tsx", ".js"}:
            return []

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []

        if "Mapping" not in content and "@router." not in content and "@app." not in content:
            return []

        if file_path.suffix.lower() in {".java", ".kt"}:
            return self._extract_spring_routes(content, rel, root)
        return self._extract_decorator_routes(content, rel)

    def _extract_dom_targets(self, file_path: Path, rel: str) -> list[dict[str, Any]]:
        suffix = file_path.suffix.lower()
        if suffix not in {".html", ".vue", ".svelte", ".jsx", ".tsx", ".js", ".ts"}:
            return []

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []

        patterns = [
            ("testid", re.compile(r"data-testid\s*=\s*[{]?['\"]([^'\"]+)['\"]")),
            ("aria-label", re.compile(r"aria-label\s*=\s*[{]?['\"]([^'\"]+)['\"]")),
            ("placeholder", re.compile(r"placeholder\s*=\s*[{]?['\"]([^'\"]+)['\"]")),
            ("name", re.compile(r"\bname\s*=\s*[{]?['\"]([^'\"]+)['\"]")),
            ("id", re.compile(r"\bid\s*=\s*[{]?['\"]([^'\"]+)['\"]")),
            ("route", re.compile(r"\bpath\s*[:=]\s*['\"]([^'\"]+)['\"]")),
        ]
        targets: list[dict[str, Any]] = []
        for line_number, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            for kind, pattern in patterns:
                for match in pattern.finditer(stripped):
                    targets.append(
                        {
                            "kind": kind,
                            "value": match.group(1),
                            "source": f"{rel}:{line_number}",
                            "hint": stripped[:180],
                        }
                    )
        return targets

    def _extract_spring_routes(self, content: str, rel: str, root: Path) -> list[dict[str, Any]]:
        lines = content.splitlines()
        routes: list[dict[str, Any]] = []
        class_prefix = self._class_mapping_prefix(lines)

        for index, raw_line in enumerate(lines):
            line = raw_line.strip()
            if "Mapping" not in line or not line.startswith("@"):
                continue

            annotation = line
            cursor = index
            while "(" in annotation and ")" not in annotation and cursor + 1 < len(lines):
                cursor += 1
                annotation += " " + lines[cursor].strip()

            method = self._spring_method(annotation)
            path = self._annotation_path(annotation)
            if not path:
                continue
            if self._is_class_mapping(lines, index, cursor):
                continue
            route_path = self._join_paths(class_prefix, path)

            summary = self._nearest_annotation_text(lines, index, "@Operation", "summary")
            log_label = self._nearest_simple_annotation_text(lines, index, "@Log")
            handler_index = self._next_handler_index(lines, cursor)
            handler = self._handler_name_at(lines[handler_index]) if handler_index is not None else None
            route = {
                "method": method,
                "path": self._normalize_path(route_path),
                "summary": summary or log_label,
                "log": log_label,
                "handler": handler,
                "source": f"{rel}:{index + 1}",
            }
            # Java Controller 上的 DTO 类型是请求契约的事实来源，必须随路由一起进入生成上下文。
            route.update(
                self.spring_contract_extractor.extract_handler_contract(
                    root,
                    content,
                    handler_index,
                    rel,
                )
            )
            routes.append(route)

        return routes

    def _extract_decorator_routes(self, content: str, rel: str) -> list[dict[str, Any]]:
        routes: list[dict[str, Any]] = []
        pattern = re.compile(r"@(router|app)\.(get|post|put|delete|patch)\(\s*['\"]([^'\"]+)['\"]")
        lines = content.splitlines()

        for index, line in enumerate(lines):
            match = pattern.search(line.strip())
            if not match:
                continue
            routes.append(
                {
                    "method": match.group(2).upper(),
                    "path": self._normalize_path(match.group(3)),
                    "summary": None,
                    "log": None,
                    "handler": self._next_handler_name(lines, index),
                    "source": f"{rel}:{index + 1}",
                }
            )

        return routes

    def _spring_method(self, annotation: str) -> str:
        match = re.search(r"@(Get|Post|Put|Delete|Patch|Request)Mapping", annotation)
        if not match:
            return "ANY"
        kind = match.group(1)
        if kind == "Request":
            method_match = re.search(r"RequestMethod\.([A-Z]+)", annotation)
            return method_match.group(1) if method_match else "ANY"
        return kind.upper()

    def _annotation_path(self, annotation: str) -> str | None:
        for key in ["value", "path"]:
            match = re.search(rf"{key}\s*=\s*['\"]([^'\"]+)['\"]", annotation)
            if match:
                return match.group(1)

        match = re.search(r"\(\s*['\"]([^'\"]+)['\"]", annotation)
        return match.group(1) if match else None

    def _nearest_annotation_text(
        self,
        lines: list[str],
        index: int,
        annotation_name: str,
        attribute_name: str,
    ) -> str | None:
        pattern = re.compile(rf"{attribute_name}\s*=\s*\"([^\"]+)\"")
        window = "\n".join(lines[max(0, index - 12) : index + 1])
        block_pattern = re.compile(
            rf"{re.escape(annotation_name)}\s*\((?P<body>.*?)\)\s*@\w+Mapping",
            re.S,
        )
        for match in reversed(list(block_pattern.finditer(window))):
            value = pattern.search(match.group("body"))
            if value:
                return value.group(1)
        for cursor in self._nearby_annotation_indexes(lines, index):
            line = lines[cursor].strip()
            if annotation_name not in line:
                continue
            match = pattern.search(line)
            if match:
                return match.group(1)
        return None

    def _nearest_simple_annotation_text(
        self,
        lines: list[str],
        index: int,
        annotation_name: str,
    ) -> str | None:
        pattern = re.compile(r"\(\s*\"([^\"]+)\"")
        for cursor in self._nearby_annotation_indexes(lines, index):
            line = lines[cursor].strip()
            if annotation_name not in line:
                continue
            match = pattern.search(line)
            if match:
                return match.group(1)
        return None

    def _nearby_annotation_indexes(self, lines: list[str], index: int) -> Iterator[int]:
        for cursor in range(index, min(len(lines), index + 8)):
            line = lines[cursor].strip()
            if cursor != index and self._looks_like_handler(line):
                break
            yield cursor

        for cursor in range(index - 1, max(-1, index - 8), -1):
            line = lines[cursor].strip()
            if line and not line.startswith("@"):
                break
            yield cursor

    def _next_handler_name(self, lines: list[str], index: int) -> str | None:
        handler_index = self._next_handler_index(lines, index)
        if handler_index is None:
            return None
        return self._handler_name_at(lines[handler_index])

    def _next_handler_index(self, lines: list[str], index: int) -> int | None:
        for cursor in range(index + 1, min(len(lines), index + 8)):
            if self._handler_name_at(lines[cursor]):
                return cursor
        return None

    def _handler_name_at(self, line: str) -> str | None:
        java_pattern = re.compile(r"\b(?:public|private|protected)\s+[\w<>, ?\[\].]+\s+(\w+)\s*\(")
        py_pattern = re.compile(r"\bdef\s+(\w+)\s*\(")
        match = java_pattern.search(line.strip()) or py_pattern.search(line.strip())
        return match.group(1) if match else None

    def _looks_like_handler(self, line: str) -> bool:
        return bool(
            re.search(r"\b(?:public|private|protected)\s+[\w<>, ?\[\].]+\s+\w+\s*\(", line)
            or re.search(r"\bdef\s+\w+\s*\(", line)
        )

    def _normalize_path(self, path: str) -> str:
        if path.startswith("/"):
            return path
        return f"/{path}"

    def _join_paths(self, prefix: str | None, path: str) -> str:
        if not prefix:
            return self._normalize_path(path)
        normalized_prefix = self._normalize_path(prefix).rstrip("/")
        normalized_path = self._normalize_path(path)
        if normalized_path == "/":
            return normalized_prefix or "/"
        return f"{normalized_prefix}{normalized_path}"

    def _class_mapping_prefix(self, lines: list[str]) -> str | None:
        """读取 Spring Controller 类级路径前缀。

        类级 `@RequestMapping` 是完整接口路径的一部分；只取方法级路径会让项目图谱
        丢失真实网关前缀。这里仅使用出现在类声明前的映射，避免误把方法注解当作前缀。
        """

        pending_mapping: str | None = None
        for index, raw_line in enumerate(lines):
            line = raw_line.strip()
            if line.startswith("@RequestMapping") and "Mapping" in line:
                annotation = line
                cursor = index
                while "(" in annotation and ")" not in annotation and cursor + 1 < len(lines):
                    cursor += 1
                    annotation += " " + lines[cursor].strip()
                pending_mapping = self._annotation_path(annotation)
                if re.search(r"\bclass\s+\w+", annotation):
                    return pending_mapping
                continue
            if re.search(r"\bclass\s+\w+", line):
                return pending_mapping
        return None

    def _is_class_mapping(self, lines: list[str], index: int, cursor: int) -> bool:
        if "@RequestMapping" not in lines[index]:
            return False
        if any(re.search(r"\bclass\s+\w+", line) for line in lines[index : cursor + 1]):
            return True
        for next_line in lines[cursor + 1 : min(len(lines), cursor + 5)]:
            stripped = next_line.strip()
            if not stripped or stripped.startswith("@"):
                continue
            return bool(re.search(r"\bclass\s+\w+", stripped))
        return False

    def _empty_scan(self) -> dict[str, Any]:
        return self._scan_stats(
            scanned_file_count=0,
            file_count=0,
            route_count=0,
            discovered_route_count=0,
            dom_target_count=0,
            discovered_dom_target_count=0,
            group_count=0,
        )

    def _scan_stats(
        self,
        *,
        scanned_file_count: int,
        file_count: int,
        route_count: int,
        discovered_route_count: int,
        dom_target_count: int,
        discovered_dom_target_count: int,
        group_count: int,
    ) -> dict[str, Any]:
        """汇总扫描覆盖率，供界面解释“图谱是否来自完整扫描”。"""

        return {
            "scanned_file_count": scanned_file_count,
            "indexed_file_count": file_count,
            "route_count": route_count,
            "discovered_route_count": discovered_route_count,
            "dom_target_count": dom_target_count,
            "discovered_dom_target_count": discovered_dom_target_count,
            "scan_group_count": group_count,
            "max_indexed_files": self.max_files,
            "max_routes": self.max_routes,
            "max_dom_targets": self.max_dom_targets,
            "max_scan_files": self.max_scan_files,
            "files_truncated": scanned_file_count > file_count,
            "routes_truncated": discovered_route_count > route_count,
            "dom_targets_truncated": discovered_dom_target_count > dom_target_count,
            "scan_truncated": False,
        }

    def _merge_duplicate_routes(self, routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """合并同方法同路径的代码路由和 Swagger 路由证据。

        控制器扫描通常有精确源码行，Swagger/OpenAPI 通常有参数和请求体契约；
        合并后 prompt 能同时看到这两类证据，避免重复端点干扰排序。
        """
        merged_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        order: list[tuple[str, str]] = []
        for route in routes:
            key = (str(route.get("method") or "GET").upper(), str(route.get("path") or ""))
            if key not in merged_by_key:
                merged_by_key[key] = dict(route)
                order.append(key)
                continue
            merged_by_key[key] = self._merge_route(merged_by_key[key], route)
        return [merged_by_key[key] for key in order]

    def _merge_route(
        self,
        existing: dict[str, Any],
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        merged = dict(existing)
        for key, value in incoming.items():
            if value in (None, "", [], {}):
                continue
            if key == "source":
                if isinstance(merged.get("source"), str):
                    self._append_unique(merged, "sources", str(merged["source"]))
                self._append_unique(merged, "sources", str(value))
                if not merged.get("source"):
                    merged["source"] = value
                continue
            if key == "source_type":
                if isinstance(merged.get("source_type"), str):
                    self._append_unique(merged, "source_types", str(merged["source_type"]))
                self._append_unique(merged, "source_types", str(value))
                if not merged.get("source_type"):
                    merged["source_type"] = value
                continue
            if key == "tags" and isinstance(value, list):
                for tag in value:
                    self._append_unique(merged, "tags", str(tag))
                continue
            if key in {"parameters", "request_body", "responses", "description"}:
                if not merged.get(key):
                    merged[key] = value
                continue
            if not merged.get(key):
                merged[key] = value
        return merged

    def _append_unique(self, target: dict[str, Any], key: str, value: str) -> None:
        values = target.get(key)
        if not isinstance(values, list):
            values = []
        if value not in values:
            values.append(value)
        target[key] = values
