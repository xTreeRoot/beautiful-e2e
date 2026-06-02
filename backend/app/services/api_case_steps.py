from __future__ import annotations

import json
import re
from typing import Any

from app.services.api_flow_variables import placeholders_in_value
from app.services.case_generation_types import GeneratedStep
from app.services.document_case_steps import clean_document_line
from app.services.reference_fixtures import (
    compact_reference_fixtures,
    extract_reference_fixtures,
    fixed_id_values,
    fixture_parameter_links_for_target,
)
from app.services.repo_reader import RepoSummary

GENERIC_ROUTE_INTENT_EXPANSIONS = {
    "登录": ("login", "signin", "sign-in", "auth"),
    "登陆": ("login", "signin", "sign-in", "auth"),
    "搜索": ("search", "query", "list", "page"),
    "查询": ("query", "search", "get", "list", "page"),
    "列表": ("list", "page", "query"),
    "分页": ("page", "list"),
    "详情": ("detail", "info", "get"),
    "查看": ("detail", "info", "get"),
    "创建": ("create", "add", "new"),
    "新增": ("create", "add", "new"),
    "提交": ("submit", "apply", "create"),
    "保存": ("save", "update"),
    "修改": ("update", "modify", "edit"),
    "更新": ("update", "modify", "edit"),
    "删除": ("delete", "remove"),
    "移除": ("delete", "remove"),
    "取消": ("cancel", "close"),
    "关闭": ("cancel", "close"),
    "预检": ("precheck", "preview", "check", "validate"),
    "校验": ("validate", "check", "verify"),
    "验证": ("validate", "check", "verify"),
}

ROUTE_TERM_STOPWORDS = {
    "api",
    "http",
    "https",
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "test",
    "case",
}


class ApiCaseStepBuilder:
    """把提示词、引用接口文档和后端路由目录转换为接口步骤。

    API 模式的职责边界比较重：文档负责给出调用链路，路由目录负责提供代码证据，
    本类只做两类证据的匹配和确定性兜底，不创建或持久化用例。
    """

    def _api_steps(
        self,
        prompt: str,
        lower: str,
        backend: RepoSummary,
        reference_documents: list[dict[str, Any]] | None = None,
    ) -> list[GeneratedStep]:
        document_steps = self._document_grounded_api_steps(
            prompt,
            backend.routes,
            reference_documents or [],
        )
        if document_steps:
            return document_steps

        route_steps = self._route_grounded_api_steps(prompt, backend.routes)
        if route_steps:
            return route_steps

        if backend.routes:
            route = backend.routes[0]
            return [
                self._route_step(
                    route,
                    label="调用首个已发现后端路由进行路由约束冒烟检查",
                    decision="提示词没有匹配到强相关路由，暂用首个已发现路由。",
                )
            ]

        return [
            GeneratedStep(
                kind="api",
                label="路由目录不可用",
                action="api_request",
                target_url="/api/health",
                expected="200",
                data={
                    "method": "GET",
                    "expected_status": 200,
                    "route_decision": (
                        "当前没有可用的后端路由目录。请配置后端仓库路径，"
                        "让生成器使用真实控制器路由。"
                    ),
                },
            )
        ]

    def _document_grounded_api_steps(
        self,
        prompt: str,
        routes: list[dict[str, Any]],
        reference_documents: list[dict[str, Any]],
    ) -> list[GeneratedStep]:
        """根据引用的接口文档和路由证据构建接口链路。

        在后端接口模式中，“客户端流程”指客户端实际消费的 HTTP 端点。
        引用文档提供顺序和固定 id，扫描到的路由目录负责把每个步骤锚定到授权项目代码。
        """
        endpoints = self._reference_api_endpoints(prompt, reference_documents)
        if not endpoints:
            return []

        reference_fixtures = extract_reference_fixtures(reference_documents)
        fixed_ids = fixed_id_values(reference_fixtures)
        compact_fixtures = compact_reference_fixtures(reference_fixtures)
        steps: list[GeneratedStep] = []
        used: set[tuple[str, str]] = set()
        for endpoint in endpoints:
            method = str(endpoint.get("method") or "GET").upper()
            path_template = str(endpoint.get("path") or "/")
            normalized_key = (method, self._route_path_signature(path_template))
            if normalized_key in used:
                continue
            used.add(normalized_key)

            route = self._matching_backend_route(method, path_template, routes)
            route_path = str(route.get("path") or path_template) if route else path_template
            label = self._reference_api_label(endpoint, route)
            target_url = self._with_gateway_prefix(
                str(endpoint.get("gateway_prefix") or ""),
                self._example_route_path(route_path, fixed_ids),
            )
            data = {
                "method": method,
                "expected_status": 200,
                "route_source": route.get("source") if route else endpoint.get("source"),
                "route_summary": (route.get("summary") or route.get("log")) if route else endpoint.get("scene"),
                "route_path_template": route_path,
                "document_path_template": path_template,
                "route_decision": (
                    "已把引用接口文档中的端点匹配到扫描出的后端路由。"
                    if route
                    else "使用引用接口文档中的端点；未找到匹配的扫描路由。"
                ),
                "reference_source": endpoint.get("source"),
                "reference_excerpt": endpoint.get("excerpt"),
                "auth": endpoint.get("auth"),
                "gateway_prefix": endpoint.get("gateway_prefix"),
                "document_grounded": True,
            }
            if compact_fixtures:
                data["reference_fixtures"] = compact_fixtures
            fixture_links = fixture_parameter_links_for_target(
                target_url=target_url,
                route_template=route_path,
                fixtures=reference_fixtures,
            )
            if fixture_links:
                data["parameter_links"] = fixture_links
            if method in {"POST", "PUT", "PATCH"}:
                data["body"] = endpoint.get("body") if isinstance(endpoint.get("body"), dict) else {}
                data["body_required"] = True
            if isinstance(endpoint.get("extract"), dict) and endpoint["extract"]:
                data["extract"] = endpoint["extract"]
                data["produces_variables"] = sorted(endpoint["extract"])

            parameter_links, unresolved_parameters = self._api_parameter_links(
                data.get("body"),
                data.get("headers"),
                target_url,
                steps,
            )
            if parameter_links:
                existing_links = data.get("parameter_links") if isinstance(data.get("parameter_links"), list) else []
                data["parameter_links"] = [*existing_links, *parameter_links]
                data["depends_on"] = parameter_links
            if unresolved_parameters:
                data["unresolved_parameters"] = unresolved_parameters

            steps.append(
                GeneratedStep(
                    kind="api",
                    label=label,
                    action="api_request",
                    target_url=target_url,
                    expected="200",
                    data=data,
                )
            )
            if len(steps) >= 20:
                break

        return steps

    def _reference_api_endpoints(
        self,
        prompt: str,
        reference_documents: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        endpoints: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for document in reference_documents:
            title = str(document.get("title") or document.get("path") or "参考文档")
            content = str(document.get("content") or "")
            gateway_prefix = self._reference_gateway_prefix(content)
            for line in content.splitlines():
                for endpoint in self._api_endpoints_from_line(line):
                    if not self._endpoint_matches_prompt(endpoint, prompt):
                        continue
                    endpoint["source"] = title
                    endpoint["gateway_prefix"] = gateway_prefix
                    key = (
                        str(endpoint.get("method") or "GET").upper(),
                        self._route_path_signature(str(endpoint.get("path") or "")),
                    )
                    if key in seen:
                        if endpoint.get("table_row"):
                            for index, existing in enumerate(endpoints):
                                existing_key = (
                                    str(existing.get("method") or "GET").upper(),
                                    self._route_path_signature(str(existing.get("path") or "")),
                                )
                                if existing_key == key and not existing.get("table_row"):
                                    endpoints[index] = endpoint
                                    break
                        continue
                    seen.add(key)
                    endpoints.append(endpoint)
        return endpoints

    def _api_endpoints_from_line(self, line: str) -> list[dict[str, Any]]:
        cells = self._markdown_table_cells(line)
        is_table_row = bool(cells)
        if not cells:
            cells = [self._clean_document_line(line)]
        if not any("/api/" in cell or "/merchant/" in cell or "/customer/" in cell for cell in cells):
            return []

        scenario = self._api_row_label(cells)
        auth = self._api_row_auth(cells)
        body = self._api_row_body(cells)
        extract = self._api_row_extract(cells)
        endpoints: list[dict[str, Any]] = []

        for cell in cells:
            for method, path in self._method_path_pairs(cell):
                if self._is_generic_api_prefix_path(path):
                    continue
                endpoints.append(
                    {
                        "scene": scenario,
                        "method": method,
                        "path": path,
                        "auth": auth or self._auth_from_path(path),
                        "excerpt": self._clean_document_line(line)[:220],
                        "table_row": is_table_row,
                        "body": body,
                        "extract": extract,
                    }
                )

        if endpoints:
            return endpoints

        methods = [
            match.group(1).upper()
            for cell in cells
            for match in re.finditer(r"\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b", cell, re.I)
        ]
        paths = [path for cell in cells for path in self._api_paths(cell)]
        if not paths:
            return []

        method = methods[0] if methods else "GET"
        return [
            {
                "scene": scenario,
                "method": method,
                "path": path,
                "auth": auth or self._auth_from_path(path),
                "excerpt": self._clean_document_line(line)[:220],
                "table_row": is_table_row,
                "body": body,
                "extract": extract,
            }
            for path in paths
            if not self._is_generic_api_prefix_path(path)
        ]

    def _api_row_body(self, cells: list[str]) -> dict[str, Any] | None:
        for cell in cells:
            for raw_object in self._json_object_candidates(cell):
                try:
                    parsed = json.loads(raw_object)
                except ValueError:
                    continue
                if isinstance(parsed, dict):
                    return parsed

        joined = " ".join(cells)
        if not any(token in joined for token in ["body", "Body", "请求体", "参数"]):
            return None

        body: dict[str, Any] = {}
        pattern = re.compile(
            r"([A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*(\{\{\s*[A-Za-z_][\w.-]*\s*\}\}|[A-Za-z0-9_.-]+)"
        )
        for match in pattern.finditer(joined):
            body[match.group(1)] = match.group(2)
        return body or None

    def _json_object_candidates(self, text: str) -> list[str]:
        candidates: list[str] = []
        for match in re.finditer(r"\{", text):
            start = match.start()
            depth = 0
            in_string = False
            escaped = False
            for index, char in enumerate(text[start:], start=start):
                if escaped:
                    escaped = False
                    continue
                if char == "\\":
                    escaped = True
                    continue
                if char == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        candidates.append(text[start : index + 1].strip("` "))
                        break
        return candidates

    def _api_row_extract(self, cells: list[str]) -> dict[str, str]:
        extract: dict[str, str] = {}
        joined = " ".join(cells)
        for match in re.finditer(
            r"([A-Za-z_][A-Za-z0-9_]*)\s*(?:=|<-|来自)\s*(\$[A-Za-z0-9_\[\].-]+)",
            joined,
        ):
            extract[match.group(1)] = match.group(2)

        if any(token in joined for token in ["返回", "响应", "输出", "提取", "extract", "Extract"]):
            for field in self._extractable_field_names(joined):
                extract.setdefault(field, f"$.data.{field}")
        return extract

    def _extractable_field_names(self, text: str) -> list[str]:
        suffixes = (
            "Id",
            "ID",
            "No",
            "Code",
            "Token",
            "Credential",
            "Key",
            "Secret",
            "Session",
            "UUID",
            "Uuid",
        )
        names: list[str] = []
        for match in re.finditer(r"`?([A-Za-z_][A-Za-z0-9_]*)`?", text):
            name = match.group(1)
            if name in {"GET", "POST", "PUT", "PATCH", "DELETE", "Body", "body"}:
                continue
            if name.endswith(suffixes) or name.lower() in {"token", "credential", "code"}:
                names.append(name)
        return list(dict.fromkeys(names))

    def _api_parameter_links(
        self,
        body: Any,
        headers: Any,
        target_url: str,
        previous_steps: list[GeneratedStep],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        requested = (
            placeholders_in_value(body)
            | placeholders_in_value(headers)
            | placeholders_in_value(target_url)
        )
        links: list[dict[str, Any]] = []
        unresolved: list[dict[str, Any]] = []
        for variable in sorted(requested):
            producer = self._previous_step_extracting(variable, previous_steps)
            if producer is None:
                unresolved.append(
                    {
                        "variable": variable,
                        "reason": "请求参数使用了变量占位符，但前置步骤尚未声明 extract。",
                    }
                )
                continue
            links.append(
                {
                    "variable": variable,
                    "from_step_label": producer.label,
                    "source": "previous_response",
                    "binding": "target_url/body/headers",
                }
            )
        return links, unresolved

    def _previous_step_extracting(
        self,
        variable: str,
        previous_steps: list[GeneratedStep],
    ) -> GeneratedStep | None:
        for step in reversed(previous_steps):
            extract = (step.data or {}).get("extract")
            if isinstance(extract, dict) and variable in extract:
                return step
        return None

    def _markdown_table_cells(self, line: str) -> list[str]:
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            return []
        if re.fullmatch(r"\|[\s:\-|]+\|", stripped):
            return []
        return [self._clean_table_cell(cell) for cell in stripped.strip("|").split("|")]

    def _clean_table_cell(self, value: str) -> str:
        return value.strip().strip("`").strip()

    def _clean_document_line(self, line: str) -> str:
        return clean_document_line(line)

    def _method_path_pairs(self, text: str) -> list[tuple[str, str]]:
        pattern = re.compile(
            r"\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b\s+"
            r"((?:/customer)?/(?:api|merchant)/[A-Za-z0-9_./{}:-]+)",
            re.I,
        )
        return [(match.group(1).upper(), match.group(2)) for match in pattern.finditer(text)]

    def _api_paths(self, text: str) -> list[str]:
        pattern = re.compile(r"(?:/customer)?/(?:api|merchant)/[A-Za-z0-9_./{}:-]+")
        return [
            path
            for match in pattern.finditer(text)
            if not self._is_generic_api_prefix_path(path := match.group(0).rstrip(".,;，。；、"))
        ]

    def _is_generic_api_prefix_path(self, path: str) -> bool:
        normalized = path.rstrip("/")
        parts = [part for part in normalized.split("/") if part]
        return parts in (["api"], ["customer", "api"], ["merchant", "api"])

    def _api_row_label(self, cells: list[str]) -> str:
        ignored = {
            "",
            "#",
            "method",
            "path",
            "路径",
            "方法",
            "登录",
            "鉴权",
            "前端主要消费",
            "主要用途",
            "用途",
            "否",
            "可选",
            "必须",
        }
        for cell in cells:
            lower = cell.lower()
            if lower in ignored or re.fullmatch(r"\d+", cell):
                continue
            if re.fullmatch(r"GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS", cell, re.I):
                continue
            if self._api_paths(cell):
                continue
            return cell[:80]
        return "引用接口步骤"

    def _api_row_auth(self, cells: list[str]) -> str | None:
        joined = " ".join(cells)
        if "必须" in joined:
            return "required"
        if "可选" in joined:
            return "optional"
        if re.search(r"(^|\s)否($|\s)", joined):
            return "none"
        return None

    def _auth_from_path(self, path: str) -> str:
        lower = path.lower()
        if any(token in lower for token in ["/admin/", "/merchant/", "/private/", "/internal/"]):
            return "required"
        return "unknown"

    def _endpoint_matches_prompt(self, endpoint: dict[str, Any], prompt: str) -> bool:
        path = str(endpoint.get("path") or "")
        text = f"{endpoint.get('scene') or ''} {path}".lower()
        if any(token in prompt for token in ["客户端", "用户端", "前端", "小程序"]):
            if "/admin/" in path or path.startswith("/merchant/"):
                return False
            if any(token in text for token in ["管理端", "商家端", "merchant", "admin"]):
                return False
        return True

    def _reference_gateway_prefix(self, content: str) -> str:
        for pattern in [
            r"客户端(?:网关|统一)?前缀[：:\s]+`([^`]+)`",
            r"\{baseUrl\}(/[^{}\s`]+)\{Path\}",
            r"\{baseUrl\}(/[^{}\s`]+)\{path\}",
        ]:
            match = re.search(pattern, content)
            if match:
                return self._normalize_gateway_prefix(match.group(1))
        return ""

    def _normalize_gateway_prefix(self, value: str) -> str:
        prefix = value.strip()
        if not prefix:
            return ""
        if not prefix.startswith("/"):
            prefix = f"/{prefix}"
        return prefix.rstrip("/")

    def _reference_fixed_ids(self, reference_documents: list[dict[str, Any]]) -> dict[str, str]:
        return fixed_id_values(extract_reference_fixtures(reference_documents))

    def _matching_backend_route(
        self,
        method: str,
        path: str,
        routes: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        signature = self._route_path_signature(path)
        for route in routes:
            route_method = str(route.get("method") or "GET").upper()
            if route_method not in {method, "ANY"}:
                continue
            if self._route_path_signature(str(route.get("path") or "")) == signature:
                return route
        return None

    def _route_path_signature(self, path: str) -> str:
        normalized = path.strip().lower()
        if normalized.startswith("/customer/"):
            normalized = normalized[len("/customer") :]
        normalized = re.sub(r"\{[^/{}]+\}", "{}", normalized)
        normalized = re.sub(r"/\d{6,}(?=/|$)", "/{}", normalized)
        return normalized.rstrip("/")

    def _reference_api_label(self, endpoint: dict[str, Any], route: dict[str, Any] | None) -> str:
        scene = str(endpoint.get("scene") or "").strip()
        summary = str((route or {}).get("summary") or (route or {}).get("log") or "").strip()
        method = str(endpoint.get("method") or "GET").upper()
        path = str(endpoint.get("path") or "/")
        if scene and summary and scene not in summary:
            return f"{scene}: {summary}"
        if scene:
            return scene
        if summary:
            return summary
        return f"{method} {path}"

    def _with_gateway_prefix(self, gateway_prefix: str, path: str) -> str:
        prefix = self._normalize_gateway_prefix(gateway_prefix)
        if not prefix or path.startswith(prefix + "/"):
            return path
        if path.startswith("/api/") or path.startswith("/merchant/"):
            return f"{prefix}{path}"
        return path

    def _route_grounded_api_steps(
        self,
        prompt: str,
        routes: list[dict[str, Any]],
    ) -> list[GeneratedStep]:
        if not routes:
            return []

        selected: list[tuple[str, dict[str, Any], str]] = []
        used: set[tuple[str, str]] = set()
        for segment in self._intent_segments(prompt):
            route = self._best_route_for_segment(segment, routes, used)
            if not route:
                continue
            key = (str(route.get("method") or "GET"), str(route.get("path") or ""))
            used.add(key)
            selected.append((segment, route, f"匹配提示词片段：{segment}"))

        return [
            self._route_step(route, label=self._route_label(segment, route), decision=decision)
            for segment, route, decision in selected[:10]
        ]

    def _intent_segments(self, prompt: str) -> list[str]:
        normalized = re.sub(r"\s+", "", prompt)
        parts = re.split(r"从|到|然后|再|并且|并|以及|和|使用|覆盖|->|=>|,|，|。|；|;", normalized)
        segments: list[str] = []
        for part in parts:
            segment = re.sub(r"(生成|一个|的|接口|模式|测试|用例|回归|全链路)+", "", part).strip()
            if len(segment) >= 2 and segment not in segments:
                segments.append(segment)
        return segments or [prompt]

    def _best_route_for_segment(
        self,
        segment: str,
        routes: list[dict[str, Any]],
        used: set[tuple[str, str]],
    ) -> dict[str, Any] | None:
        terms = self._expanded_route_terms(segment)
        segment_lower = segment.lower()
        best: tuple[int, int, dict[str, Any]] | None = None
        for route in routes:
            key = (str(route.get("method") or "GET"), str(route.get("path") or ""))
            if key in used:
                continue

            searchable = self._route_search_text(route)
            score = sum(3 if term == segment_lower else 1 for term in terms if term in searchable)
            if score <= 0:
                continue
            if any(term in str(route.get("path") or "").lower() for term in terms):
                score += 2
            preference = self._route_preference_score(segment, route)
            rank = score + preference
            if best is None or (rank, score) > (best[0], best[1]):
                best = (rank, score, route)

        return best[2] if best and best[0] >= 2 else None

    def _expanded_route_terms(self, segment: str) -> list[str]:
        terms: list[str] = [segment.lower()]
        terms.extend(self._lexical_route_terms(segment))
        for token, values in GENERIC_ROUTE_INTENT_EXPANSIONS.items():
            if token in segment:
                terms.extend(values)

        chinese_terms = re.findall(r"[\u4e00-\u9fff]{2,}", segment)
        for term in chinese_terms:
            terms.append(term)
            if len(term) > 2:
                terms.extend(term[index : index + 2] for index in range(len(term) - 1))

        return list(dict.fromkeys(term for term in terms if term))

    def _lexical_route_terms(self, text: str) -> list[str]:
        normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
        parts = re.split(r"[^A-Za-z0-9]+", normalized.lower())
        terms = [part for part in parts if len(part) >= 2 and part not in ROUTE_TERM_STOPWORDS]
        for term in list(terms):
            terms.extend(self._english_plural_variants(term))
        return list(dict.fromkeys(terms))

    def _english_plural_variants(self, term: str) -> list[str]:
        if not re.fullmatch(r"[a-z][a-z0-9]*", term):
            return []
        if len(term) <= 3:
            return []
        if term.endswith("ies"):
            return [term[:-3] + "y"]
        if term.endswith("s"):
            return [term[:-1]]
        return [term + "s"]

    def _route_search_text(self, route: dict[str, Any]) -> str:
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
        ]
        return " ".join(str(value or "") for value in values).lower()

    def _route_preference_score(self, segment: str, route: dict[str, Any]) -> int:
        text = self._route_search_text(route)
        method = str(route.get("method") or "GET").upper()
        score = 0
        if "admin" in text and "管理" not in segment and "后台" not in segment and "admin" not in segment.lower():
            score -= 5
        if any(token in text for token in ["merchant", "proprietor"]) and not any(
            token in segment for token in ["商户", "管理", "后台", "merchant", "proprietor"]
        ):
            score -= 5
        if any(token in text for token in ["callback", "notify", "notification", "通知", "回调"]) and not any(
            token in segment.lower() for token in ["callback", "notify", "通知", "回调"]
        ):
            score -= 4
        if any(token in text for token in ["option", "options", "enum", "枚举", "选项"]) and not any(
            token in segment.lower() for token in ["option", "enum", "类型", "选项", "枚举"]
        ):
            score -= 2
        if method == "GET" and any(token in segment for token in ["查询", "搜索", "列表", "详情", "查看"]):
            score += 1
        if method in {"POST", "PUT", "PATCH"} and any(
            token in segment for token in ["创建", "新增", "提交", "保存", "修改", "更新", "发起", "确认"]
        ):
            score += 1
        if method == "DELETE" and any(token in segment for token in ["删除", "移除"]):
            score += 1
        return score

    def _route_step(
        self,
        route: dict[str, Any],
        label: str,
        decision: str,
    ) -> GeneratedStep:
        method = str(route.get("method") or "GET").upper()
        path = str(route.get("path") or "/")
        data = self._route_step_data(route, method, path, decision)
        return GeneratedStep(
            kind="api",
            label=label,
            action="api_request",
            target_url=self._example_route_path(path, self._route_path_examples(route)),
            expected="200",
            data=data,
        )

    def _route_step_data(
        self,
        route: dict[str, Any],
        method: str,
        path: str,
        decision: str,
    ) -> dict[str, Any]:
        """把路由目录中的 Swagger 扩展字段带进可编辑接口步骤。

        这些字段不会直接影响运行器，但会保留在用例 DSL 中，方便用户和模型继续
        根据参数、请求体、响应结构补齐接口链路。
        """
        data: dict[str, Any] = {
            "method": method if method != "ANY" else "GET",
            "expected_status": 200,
            "route_source": route.get("source"),
            "route_summary": route.get("summary") or route.get("log"),
            "route_path_template": path,
            "route_decision": decision,
        }
        optional_fields = {
            "source_type": "route_source_type",
            "sources": "route_sources",
            "source_types": "route_source_types",
            "tags": "route_tags",
            "description": "route_description",
            "parameters": "route_parameters",
            "request_body": "route_request_body",
            "responses": "route_responses",
        }
        for route_key, data_key in optional_fields.items():
            if route.get(route_key):
                data[data_key] = route[route_key]

        request_body = route.get("request_body")
        if isinstance(request_body, dict) and method in {"POST", "PUT", "PATCH"}:
            if "example" in request_body:
                data["body"] = request_body["example"]
            if request_body.get("required"):
                data["body_required"] = True
        return data

    def _route_path_examples(self, route: dict[str, Any]) -> dict[str, str]:
        examples: dict[str, str] = {}
        parameters = route.get("parameters")
        if not isinstance(parameters, list):
            return examples
        for parameter in parameters:
            if not isinstance(parameter, dict):
                continue
            if str(parameter.get("in") or "").lower() != "path":
                continue
            name = str(parameter.get("name") or "")
            example = parameter.get("example")
            if name and example is not None:
                examples[name] = str(example)
        return examples

    def _route_label(self, segment: str, route: dict[str, Any]) -> str:
        summary = route.get("summary") or route.get("log") or route.get("handler")
        if summary:
            return f"{segment}: {summary}"
        return f"{segment}: {route.get('method', 'GET')} {route.get('path', '/')}"

    def _example_route_path(self, path: str, fixed_ids: dict[str, str] | None = None) -> str:
        values = fixed_ids or {}

        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            return values.get(name) or values.get(name[0].lower() + name[1:]) or "1"

        return re.sub(r"\{([^/{}]+)\}", replace, path)
