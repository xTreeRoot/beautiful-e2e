from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    import yaml
except ImportError:  # pragma: no cover - uvicorn[standard] normally provides PyYAML.
    yaml = None


HTTP_METHODS = {"get", "post", "put", "delete", "patch", "head", "options", "trace"}
MAX_OPENAPI_BYTES = 2 * 1024 * 1024
MAX_SCHEMA_DEPTH = 4


class OpenApiRouteExtractor:
    """把 Swagger/OpenAPI 文档转换为仓库路由目录。

    输出字段兼容 `RepoSummary.routes`，这样项目分析和后续 prompt 构建都能复用
    同一份真实接口证据；请求参数、请求体和响应结构保留为附加字段，供模型推导
    接口链路和参数来源。
    """

    def extract(self, file_path: Path, rel: str) -> list[dict[str, Any]]:
        if not self._looks_like_openapi_file(file_path):
            return []
        if self._is_too_large(file_path):
            return []

        document = self._load_document(file_path)
        if not self._is_openapi_document(document):
            return []

        paths = document.get("paths")
        if not isinstance(paths, Mapping):
            return []

        source_type = "swagger" if document.get("swagger") else "openapi"
        base_path = self._document_base_path(document)
        routes: list[dict[str, Any]] = []
        for raw_path, raw_path_item in paths.items():
            if not isinstance(raw_path, str) or not isinstance(raw_path_item, Mapping):
                continue

            path_item = self._resolve_ref(raw_path_item, document)
            if not isinstance(path_item, Mapping):
                continue

            common_parameters = self._parameter_items(path_item.get("parameters"), document)
            for raw_method, raw_operation in path_item.items():
                method = str(raw_method).lower()
                if method not in HTTP_METHODS:
                    continue
                operation = self._resolve_ref(raw_operation, document)
                if not isinstance(operation, Mapping):
                    continue

                operation_parameters = self._parameter_items(operation.get("parameters"), document)
                parameters = common_parameters + operation_parameters
                route = self._route_from_operation(
                    method=method.upper(),
                    path=self._join_paths(base_path, raw_path),
                    operation=operation,
                    parameters=parameters,
                    document=document,
                    source_type=source_type,
                    source=f"{rel}:paths.{raw_path}.{method}",
                )
                routes.append(route)

        return routes

    def _route_from_operation(
        self,
        *,
        method: str,
        path: str,
        operation: Mapping[str, Any],
        parameters: list[Mapping[str, Any]],
        document: Mapping[str, Any],
        source_type: str,
        source: str,
    ) -> dict[str, Any]:
        summary = self._compact_text(operation.get("summary"))
        description = self._compact_text(operation.get("description"))
        operation_id = self._compact_text(operation.get("operationId"))
        route: dict[str, Any] = {
            "method": method,
            "path": self._normalize_path(path),
            "summary": summary or operation_id or description,
            "log": None,
            "handler": operation_id,
            "source": source,
            "source_type": source_type,
        }

        raw_tags = operation.get("tags")
        tags = [str(tag) for tag in raw_tags if isinstance(tag, str)] if isinstance(raw_tags, list) else []
        if tags:
            route["tags"] = tags[:8]
        if description and description != route["summary"]:
            route["description"] = description

        parameter_summaries = self._parameter_summaries(parameters, document)
        if parameter_summaries:
            route["parameters"] = parameter_summaries

        request_body = self._request_body_summary(operation, parameters, document)
        if request_body:
            route["request_body"] = request_body

        responses = self._response_summaries(operation, document)
        if responses:
            route["responses"] = responses

        return route

    def _looks_like_openapi_file(self, file_path: Path) -> bool:
        suffix = file_path.suffix.lower()
        return suffix in {".json", ".yaml", ".yml"}

    def _is_too_large(self, file_path: Path) -> bool:
        try:
            return file_path.stat().st_size > MAX_OPENAPI_BYTES
        except OSError:
            return True

    def _load_document(self, file_path: Path) -> Mapping[str, Any] | None:
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return None

        suffix = file_path.suffix.lower()
        parse_errors: tuple[type[BaseException], ...] = (ValueError, TypeError)
        if yaml is not None:
            parse_errors = (*parse_errors, yaml.YAMLError)
        try:
            if suffix == ".json":
                loaded = json.loads(content)
            elif yaml is not None:
                loaded = self._load_yaml_document(content)
            else:
                return None
        except parse_errors:
            return None

        return loaded if isinstance(loaded, Mapping) else None

    def _load_yaml_document(self, content: str) -> Mapping[str, Any] | None:
        for loaded in yaml.safe_load_all(content):
            if not isinstance(loaded, Mapping):
                continue
            if self._is_openapi_document(loaded):
                return loaded
        return None

    def _is_openapi_document(self, document: Mapping[str, Any] | None) -> bool:
        if not isinstance(document, Mapping):
            return False
        if not isinstance(document.get("paths"), Mapping):
            return False
        return bool(document.get("openapi") or document.get("swagger"))

    def _document_base_path(self, document: Mapping[str, Any]) -> str:
        base_path = self._compact_text(document.get("basePath"))
        if base_path:
            return base_path

        servers = document.get("servers")
        if not isinstance(servers, list) or not servers:
            return ""
        first_server = servers[0]
        if not isinstance(first_server, Mapping):
            return ""
        url = self._compact_text(first_server.get("url"))
        if not url:
            return ""

        parsed = urlparse(url)
        path = parsed.path if parsed.scheme or parsed.netloc else url
        path = path.split("{", 1)[0].rstrip("/")
        return path if path.startswith("/") else ""

    def _join_paths(self, base_path: str, route_path: str) -> str:
        base = self._normalize_path(base_path).rstrip("/") if base_path else ""
        route = self._normalize_path(route_path)
        if not base or route.startswith(base + "/") or route == base:
            return route
        return f"{base}{route}"

    def _parameter_items(
        self,
        raw_parameters: Any,
        document: Mapping[str, Any],
    ) -> list[Mapping[str, Any]]:
        if not isinstance(raw_parameters, list):
            return []
        items: list[Mapping[str, Any]] = []
        for raw_parameter in raw_parameters:
            parameter = self._resolve_ref(raw_parameter, document)
            if isinstance(parameter, Mapping):
                items.append(parameter)
        return items

    def _parameter_summaries(
        self,
        parameters: list[Mapping[str, Any]],
        document: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for parameter in parameters:
            name = self._compact_text(parameter.get("name"))
            location = self._compact_text(parameter.get("in"))
            if not name or not location:
                continue
            key = (location, name)
            if key in seen:
                continue
            seen.add(key)

            schema = self._schema_summary(parameter.get("schema"), document)
            summary: dict[str, Any] = {
                "name": name,
                "in": location,
                "required": bool(parameter.get("required") or location == "path"),
            }
            if schema:
                summary["schema"] = schema
            description = self._compact_text(parameter.get("description"))
            if description:
                summary["description"] = description
            example = self._explicit_example(parameter, schema)
            if example is not None:
                summary["example"] = example
            summaries.append(summary)
        return summaries

    def _request_body_summary(
        self,
        operation: Mapping[str, Any],
        parameters: list[Mapping[str, Any]],
        document: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        request_body = self._resolve_ref(operation.get("requestBody"), document)
        if isinstance(request_body, Mapping):
            summary = self._request_body_from_content(request_body, document)
            if summary:
                return summary

        body_parameter = next(
            (
                parameter
                for parameter in parameters
                if (self._compact_text(parameter.get("in")) or "").lower() == "body"
            ),
            None,
        )
        if body_parameter is not None:
            schema = self._schema_summary(body_parameter.get("schema"), document)
            summary = {
                "required": bool(body_parameter.get("required")),
                "content_type": "application/json",
            }
            if schema:
                summary["schema"] = schema
            example = self._explicit_example(body_parameter, schema)
            if example is not None:
                summary["example"] = example
            return summary

        form_parameters = [
            parameter
            for parameter in parameters
            if (self._compact_text(parameter.get("in")) or "").lower() == "formdata"
        ]
        if form_parameters:
            return {
                "required": any(bool(parameter.get("required")) for parameter in form_parameters),
                "content_type": "application/x-www-form-urlencoded",
                "fields": self._parameter_summaries(form_parameters, document),
            }
        return None

    def _request_body_from_content(
        self,
        request_body: Mapping[str, Any],
        document: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        content = request_body.get("content")
        if not isinstance(content, Mapping) or not content:
            return None

        content_type = self._preferred_content_type(content)
        media = content.get(content_type)
        if not isinstance(media, Mapping):
            return None

        schema = self._schema_summary(media.get("schema"), document)
        summary: dict[str, Any] = {
            "required": bool(request_body.get("required")),
            "content_type": content_type,
        }
        if schema:
            summary["schema"] = schema
        example = self._media_example(media, schema)
        if example is not None:
            summary["example"] = example
        return summary

    def _preferred_content_type(self, content: Mapping[str, Any]) -> str:
        for content_type in ["application/json", "application/*+json"]:
            if content_type in content:
                return content_type
        for content_type in content:
            return str(content_type)
        return "application/json"

    def _response_summaries(
        self,
        operation: Mapping[str, Any],
        document: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        responses = operation.get("responses")
        if not isinstance(responses, Mapping):
            return []

        summaries: list[dict[str, Any]] = []
        for status, raw_response in responses.items():
            response = self._resolve_ref(raw_response, document)
            if not isinstance(response, Mapping):
                continue
            summary: dict[str, Any] = {"status": str(status)}
            description = self._compact_text(response.get("description"))
            if description:
                summary["description"] = description

            content = response.get("content")
            if isinstance(content, Mapping) and content:
                content_type = self._preferred_content_type(content)
                media = content.get(content_type)
                if isinstance(media, Mapping):
                    schema = self._schema_summary(media.get("schema"), document)
                    if schema:
                        summary["content_type"] = content_type
                        summary["schema"] = schema
            elif isinstance(response.get("schema"), Mapping):
                schema = self._schema_summary(response.get("schema"), document)
                if schema:
                    summary["content_type"] = "application/json"
                    summary["schema"] = schema

            summaries.append(summary)
            if len(summaries) >= 6:
                break
        return summaries

    def _schema_summary(
        self,
        raw_schema: Any,
        document: Mapping[str, Any],
        depth: int = 0,
    ) -> dict[str, Any]:
        schema = self._resolve_ref(raw_schema, document)
        if not isinstance(schema, Mapping) or depth > MAX_SCHEMA_DEPTH:
            return {}

        summary: dict[str, Any] = {}
        for key in ["type", "format", "description", "nullable"]:
            value = schema.get(key)
            if isinstance(value, (str, bool)):
                summary[key] = value
        if isinstance(schema.get("enum"), list):
            summary["enum"] = schema["enum"][:12]
        if isinstance(schema.get("required"), list):
            summary["required"] = [str(item) for item in schema["required"][:24]]
        if "example" in schema:
            summary["example"] = schema["example"]
        elif "default" in schema:
            summary["default"] = schema["default"]

        properties = schema.get("properties")
        if isinstance(properties, Mapping) and depth < MAX_SCHEMA_DEPTH:
            summary["properties"] = {
                str(name): self._schema_summary(value, document, depth + 1)
                for name, value in list(properties.items())[:24]
            }

        items = schema.get("items")
        if isinstance(items, Mapping) and depth < MAX_SCHEMA_DEPTH:
            summary["items"] = self._schema_summary(items, document, depth + 1)

        for composition_key in ["allOf", "oneOf", "anyOf"]:
            values = schema.get(composition_key)
            if isinstance(values, list) and depth < MAX_SCHEMA_DEPTH:
                summary[composition_key] = [
                    self._schema_summary(value, document, depth + 1) for value in values[:6]
                ]

        return {key: value for key, value in summary.items() if value not in ({}, [], None, "")}

    def _resolve_ref(self, value: Any, document: Mapping[str, Any]) -> Any:
        if not isinstance(value, Mapping) or not isinstance(value.get("$ref"), str):
            return value
        ref = value["$ref"]
        if not ref.startswith("#/"):
            return value

        current: Any = document
        for raw_part in ref[2:].split("/"):
            part = raw_part.replace("~1", "/").replace("~0", "~")
            if not isinstance(current, Mapping) or part not in current:
                return value
            current = current[part]
        return current

    def _media_example(self, media: Mapping[str, Any], schema: dict[str, Any]) -> Any:
        if "example" in media:
            return media["example"]
        examples = media.get("examples")
        if isinstance(examples, Mapping):
            for raw_example in examples.values():
                example = raw_example
                if isinstance(raw_example, Mapping) and "value" in raw_example:
                    example = raw_example["value"]
                if example is not None:
                    return example
        return self._explicit_example(media, schema)

    def _explicit_example(self, item: Mapping[str, Any], schema: dict[str, Any]) -> Any:
        if "example" in item:
            return item["example"]
        if "default" in item:
            return item["default"]
        if "example" in schema:
            return schema["example"]
        if "default" in schema:
            return schema["default"]
        return None

    def _compact_text(self, value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        text = " ".join(value.split())
        return text[:300] if text else None

    def _normalize_path(self, path: str) -> str:
        if not path:
            return ""
        return path if path.startswith("/") else f"/{path}"
