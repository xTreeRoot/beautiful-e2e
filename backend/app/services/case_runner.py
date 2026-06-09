from __future__ import annotations

from dataclasses import dataclass
import json
from time import perf_counter
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from app.models import TestCase, TestStep
from app.services.api_flow_variables import (
    extract_response_variables,
    placeholders_in_value,
    resolve_dynamic_value,
)
from app.services.environment_auth import has_non_empty_header
from app.services.project_environments import DEFAULT_API_BASE_URL

ALLOWED_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
MAX_RESPONSE_PREVIEW_BYTES = 64 * 1024
MAX_RESPONSE_PREVIEW_CHARS = 4000


@dataclass(frozen=True)
class ApiRequestSpec:
    step_id: str
    order_index: int
    label: str
    method: str
    url: str
    expected_status: int
    headers: dict[str, str]
    body: Any = None
    extract: Any = None

    def event_payload(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "order_index": self.order_index,
            "label": self.label,
            "method": self.method,
            "url": self.url,
            "expected_status": self.expected_status,
            "request_header_count": len(self.headers),
        }


@dataclass(frozen=True)
class ApiHttpResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes


@dataclass(frozen=True)
class ApiStepRunResult:
    step_id: str
    order_index: int
    label: str
    method: str
    url: str
    expected_status: int
    status_code: int | None
    duration_ms: int
    ok: bool
    error: str | None = None
    response_preview: str = ""
    response_content_type: str | None = None
    extracted_variables: dict[str, Any] | None = None

    def event_payload(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "order_index": self.order_index,
            "label": self.label,
            "method": self.method,
            "url": self.url,
            "expected_status": self.expected_status,
            "status_code": self.status_code,
            "duration_ms": self.duration_ms,
            "ok": self.ok,
            "error": self.error,
            "response_preview": self.response_preview,
            "response_content_type": self.response_content_type,
            "extracted_variable_names": sorted((self.extracted_variables or {}).keys()),
        }


class ApiCaseRunner:
    """按用例中的 api_request 步骤真实发送 HTTP 请求。

    服务只返回可展示的请求摘要和响应预览，不回传请求头值，避免认证信息在
    前端运行面板里被意外暴露。
    """

    def __init__(
        self,
        *,
        api_base_url: str = DEFAULT_API_BASE_URL,
        request_headers: dict[str, Any] | None = None,
        timeout_seconds: float = 20.0,
        request_sender: Callable[[ApiRequestSpec], ApiHttpResponse] | None = None,
    ) -> None:
        self.api_base_url = (api_base_url or DEFAULT_API_BASE_URL).strip()
        self.request_headers = self._normalize_headers(request_headers or {})
        self.timeout_seconds = timeout_seconds
        self._request_sender = request_sender or self._send_with_urllib

    def executable_steps(self, case: TestCase) -> list[TestStep]:
        """返回当前后端接口运行器能够执行的步骤，保持用例原始顺序。"""

        return [step for step in case.steps if step.action == "api_request"]

    def build_request(
        self,
        step: TestStep,
        variables: dict[str, Any] | None = None,
    ) -> ApiRequestSpec:
        """把持久化步骤转换成单次 HTTP 请求契约。

        `variables` 来自前置接口响应的 `extract`，会解析 URL、headers 和 body 中的
        `{{变量}}` 占位符，确保链式接口不是只在图上连线。
        """

        data = step.data or {}
        flow_variables = variables or {}
        method = str(data.get("method") or "GET").strip().upper()
        if method not in ALLOWED_HTTP_METHODS:
            raise ValueError(f"不支持的请求方法：{method}")

        target = str(step.target_url or step.selector or "").strip()
        if not target:
            raise ValueError("接口步骤缺少 URL")
        target = str(resolve_dynamic_value(target, flow_variables))

        expected_status = (
            _status_code_from_unknown(data.get("expected_status"))
            or _status_code_from_unknown(step.expected)
            or 200
        )
        headers = dict(self.request_headers)
        step_headers = data.get("headers")
        if isinstance(step_headers, dict):
            step_headers = self._headers_without_environment_overrides(
                step_headers,
                flow_variables,
            )
            step_headers = self._headers_without_missing_optional_variables(
                step_headers,
                flow_variables,
                data,
            )
            resolved_headers = resolve_dynamic_value(step_headers, flow_variables)
            if isinstance(resolved_headers, dict):
                headers.update(
                    {
                        str(key): "" if value is None else str(value)
                        for key, value in resolved_headers.items()
                    }
                )

        body = data.get("body") if "body" in data else None
        if body is not None:
            body = resolve_dynamic_value(body, flow_variables)

        return ApiRequestSpec(
            step_id=step.id,
            order_index=step.order_index,
            label=step.label,
            method=method,
            url=self._absolute_url(target),
            expected_status=expected_status,
            headers=headers,
            body=body,
            extract=data.get("extract"),
        )

    def run_request(self, spec: ApiRequestSpec) -> ApiStepRunResult:
        """执行单个请求并把网络错误转换为可展示的步骤结果。"""

        started_at = perf_counter()
        try:
            response = self._request_sender(spec)
            duration_ms = int((perf_counter() - started_at) * 1000)
            content_type = _header_value(response.headers, "content-type")
            preview = _response_preview(response.body)
            status_matches = response.status_code == spec.expected_status
            extracted_variables = (
                extract_response_variables(response.body, spec.extract) if status_matches else {}
            )
            return ApiStepRunResult(
                step_id=spec.step_id,
                order_index=spec.order_index,
                label=spec.label,
                method=spec.method,
                url=spec.url,
                expected_status=spec.expected_status,
                status_code=response.status_code,
                duration_ms=duration_ms,
                ok=status_matches,
                error=None if status_matches else "响应状态码不符合期望",
                response_preview=preview,
                response_content_type=content_type,
                extracted_variables=extracted_variables,
            )
        except Exception as exc:
            duration_ms = int((perf_counter() - started_at) * 1000)
            return self.build_error_result(spec, str(exc), duration_ms=duration_ms)

    def build_error_result(
        self,
        spec: ApiRequestSpec,
        error: str,
        *,
        duration_ms: int = 0,
    ) -> ApiStepRunResult:
        return ApiStepRunResult(
            step_id=spec.step_id,
            order_index=spec.order_index,
            label=spec.label,
            method=spec.method,
            url=spec.url,
            expected_status=spec.expected_status,
            status_code=None,
            duration_ms=duration_ms,
            ok=False,
            error=error,
        )

    def build_step_error_result(self, step: TestStep, error: str) -> ApiStepRunResult:
        return ApiStepRunResult(
            step_id=step.id,
            order_index=step.order_index,
            label=step.label,
            method=str((step.data or {}).get("method") or "GET").upper(),
            url=str(step.target_url or step.selector or ""),
            expected_status=_status_code_from_unknown(step.expected) or 200,
            status_code=None,
            duration_ms=0,
            ok=False,
            error=error,
        )

    def _absolute_url(self, target: str) -> str:
        target = _environment_relative_target(target)
        return _join_environment_base_url(self.api_base_url, target)

    def _send_with_urllib(self, spec: ApiRequestSpec) -> ApiHttpResponse:
        headers, body = _encode_body(spec.headers, spec.body)
        request = Request(spec.url, data=body, headers=headers, method=spec.method)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return ApiHttpResponse(
                    status_code=response.status,
                    headers=dict(response.headers.items()),
                    body=response.read(MAX_RESPONSE_PREVIEW_BYTES + 1),
                )
        except HTTPError as exc:
            return ApiHttpResponse(
                status_code=exc.code,
                headers=dict(exc.headers.items()),
                body=exc.read(MAX_RESPONSE_PREVIEW_BYTES + 1),
            )
        except TimeoutError as exc:
            raise RuntimeError("请求超时") from exc
        except URLError as exc:
            reason = getattr(exc, "reason", exc)
            raise RuntimeError(f"请求失败：{reason}") from exc

    def _normalize_headers(self, headers: dict[str, Any]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for key, value in headers.items():
            key_text = str(key).strip()
            if not key_text:
                continue
            normalized[key_text] = "" if value is None else str(value)
        return normalized

    def _headers_without_missing_optional_variables(
        self,
        headers: dict[str, Any],
        variables: dict[str, Any],
        step_data: dict[str, Any],
    ) -> dict[str, Any]:
        """可选登录态缺失时省略对应 header，避免公开接口被前置登录卡死。

        路径和请求体里的缺失变量仍会失败；这里只有 `depends_on` 或
        `parameter_links` 明确标记 `required=false` 的 header 会被跳过。
        """

        optional_variables = _optional_header_variables(step_data)
        if not optional_variables:
            return headers

        filtered: dict[str, Any] = {}
        for key, value in headers.items():
            missing = placeholders_in_value(value) - set(variables)
            if missing and missing.issubset(optional_variables):
                continue
            filtered[key] = value
        return filtered

    def _headers_without_environment_overrides(
        self,
        headers: dict[str, Any],
        variables: dict[str, Any],
    ) -> dict[str, Any]:
        """环境已提供同名 header 时，跳过 DSL 中未解析的 header 占位符。

        这层只处理请求头，不处理 URL 或 Body。认证 token 可能来自小程序、扫码或
        手工复制的环境值，不能强制要求前置接口生产；业务参数仍必须由变量链路解析。
        """

        filtered: dict[str, Any] = {}
        known_variables = set(variables)
        for key, value in headers.items():
            missing = placeholders_in_value(value) - known_variables
            if missing and has_non_empty_header(self.request_headers, str(key)):
                continue
            filtered[key] = value
        return filtered


def _encode_body(headers: dict[str, str], body: Any) -> tuple[dict[str, str], bytes | None]:
    encoded_headers = dict(headers)
    if body is None:
        return encoded_headers, None

    if isinstance(body, bytes):
        return encoded_headers, body
    if isinstance(body, str):
        _set_default_header(encoded_headers, "Content-Type", "text/plain; charset=utf-8")
        return encoded_headers, body.encode("utf-8")

    _set_default_header(encoded_headers, "Content-Type", "application/json")
    return encoded_headers, json.dumps(body, ensure_ascii=False).encode("utf-8")


def _set_default_header(headers: dict[str, str], key: str, value: str) -> None:
    if any(existing.lower() == key.lower() for existing in headers):
        return
    headers[key] = value


def _header_value(headers: dict[str, str], key: str) -> str | None:
    key_lower = key.lower()
    for header_key, value in headers.items():
        if header_key.lower() == key_lower:
            return value
    return None


def _environment_relative_target(target: str) -> str:
    """把节点里的完整 URL 收敛成路径契约，运行时再挂到当前项目环境。

    接口节点可能来自历史生成结果或用户调试草稿，里面残留的 host 不能覆盖
    当前项目选择的接口基础地址；query 和 fragment 仍属于接口目标，需要保留。
    """

    parsed = urlsplit(target)
    if not (parsed.scheme or parsed.netloc):
        return target
    path = parsed.path or "/"
    return urlunsplit(("", "", path, parsed.query, parsed.fragment))


def _join_environment_base_url(base_url: str, target: str) -> str:
    """按项目配置前缀拼接接口目标。

    `urllib.parse.urljoin` 会在 target 以 `/` 开头时丢弃 base_url 的路径，
    但项目里的接口基础地址可能就是网关前缀，所以这里按“配置值是前缀”的语义拼接。
    """

    base = base_url.rstrip("/")
    target = target.strip()
    if not target:
        return base

    parsed_base = urlsplit(base)
    base_path = parsed_base.path.rstrip("/")
    if base_path and (target == base_path or target.startswith(f"{base_path}/")):
        origin = urlunsplit((parsed_base.scheme, parsed_base.netloc, "", "", ""))
        if origin:
            return f"{origin}{target}"

    if target.startswith(("/", "?", "#")):
        return f"{base}{target}"
    return f"{base}/{target}"


def _response_preview(body: bytes) -> str:
    text = body[:MAX_RESPONSE_PREVIEW_BYTES].decode("utf-8", errors="replace")
    if len(text) > MAX_RESPONSE_PREVIEW_CHARS:
        return f"{text[:MAX_RESPONSE_PREVIEW_CHARS]}..."
    return text


def _status_code_from_unknown(value: Any) -> int | None:
    if isinstance(value, int) and 100 <= value <= 599:
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.isdigit():
        status = int(text)
        return status if 100 <= status <= 599 else None
    return None


def _optional_header_variables(step_data: dict[str, Any]) -> set[str]:
    optional: set[str] = set()
    for collection_key in ("depends_on", "parameter_links"):
        items = step_data.get(collection_key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict) or item.get("required") is not False:
                continue
            location = str(item.get("location") or item.get("field") or "")
            if "header" not in location.lower() and "Authorization" not in location:
                continue
            variable = item.get("variable") or item.get("source_variable")
            if variable:
                optional.add(str(variable))
    return optional
